"""
Fully annotated: Simple AI Voice Agent for Outbound Calls via Twilio + LiveKit

Run:
- python outbound_agent_annotated.py        # creates SIP trunk and initiates outbound call
- python outbound_agent_annotated.py agent  # runs an agent worker which joins the LiveKit room and handles the call

This file is the original script expanded with detailed, line-by-line comments explaining:
- what each import provides,
- what each variable contains,
- what each function, class, parameter, and object does,
- how the pieces fit together (LiveKit API, SIP trunk, AgentSession, STT/LLM/TTS/VAD, etc.)
"""
# Standard library imports
import asyncio               # asyncio: Python's library for writing asynchronous code using coroutines.
                             # Used here because LiveKit SDK and network operations are async.
import os                    # os: access environment variables and filesystem.
from dotenv import load_dotenv
                             # load_dotenv: convenience to load environment variables from a .env file
                             # into os.environ (useful for local development).

# ============================================================================
# Third-party / SDK imports from LiveKit Python integration
# ============================================================================
# `livekit` is the SDK provided by LiveKit for interacting with LiveKit servers and
# building agent workers. Specific modules:
from livekit import agents, rtc, api
                             # agents: runtime for agent workers (worker CLI, job context, subscriptions)
                             # rtc: real-time transport utilities (not explicitly used line-by-line here
                             #      but commonly available for advanced track handling).
                             # api: synchronous/asynchronous HTTP API client for LiveKit server operations
                             #      (create trunks, create participants, manage rooms, etc.)

from livekit.agents import AgentSession, Agent
                             # AgentSession: high-level orchestration object that ties together
                             # a room, an Agent implementation, and provider plugins (STT/LLM/TTS/VAD).
                             # Agent: base class representing an LLM-driven conversational agent.
                             #        You subclass it to give the model instructions and custom behavior.

# Plugins: adapters to external providers for STT/LLM/TTS/VAD
from livekit.plugins import aws, google, deepgram, silero
                             # aws: plugin wrapper used for AWS services such as Polly TTS.
                             # google: plugin wrapper used for Google LLMs (Gemini) in this example.
                             # deepgram: plugin wrapper used for Deepgram real-time STT.
                             # silero: local/packaged VAD (voice activity detection) implementation.

from livekit.plugins.turn_detector.multilingual import MultilingualModel
                             # MultilingualModel: a turn-detection model that detects speaker-turn boundaries
                             # across languages. Used to avoid overlapping speech (agent vs. human).

from livekit.protocol import sip as proto_sip
                             # proto_sip: protocol types / request objects for LiveKit's SIP API endpoints.
                             # Used to construct strongly-typed requests for creating trunks and participants.

# Load environment variables from a .env file (if present).
# This makes local testing easier by storing secrets in a file instead of the environment.
load_dotenv()

# ============================================================================
# CONFIGURATION - environment variables and what each one represents
# ============================================================================
# LiveKit server address and API credentials (used for provisioning trunks and participants)
LIVEKIT_URL = os.getenv("LIVEKIT_URL")
# - Example: "https://your-livekit-domain.com" or "https://livekit.example.com:7880"
# - Used by api.LiveKitAPI to send HTTP requests to your LiveKit instance.

LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
# - LiveKit publishable or admin API key depending on your server configuration.

LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")
# - LiveKit API secret to sign requests made via api.LiveKitAPI.
# - Must be kept secret (do not commit to source control).

# Twilio or SIP provider details used to route outbound calls through the SIP trunk
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
# - The phone number associated with the Twilio trunk or number you will present as the caller ID.

TWILIO_SIP_DOMAIN = os.getenv("TWILIO_SIP_DOMAIN")
# - The SIP domain/address for your SIP provider (e.g., "sip.example.pstn.twilio.com")

TWILIO_SIP_USERNAME = os.getenv("TWILIO_SIP_USERNAME")
# - The username used for SIP authentication (if your trunk requires authentication).

TWILIO_SIP_PASSWORD = os.getenv("TWILIO_SIP_PASSWORD")
# - The password used for SIP authentication (if your trunk requires authentication).

# Target phone number to call (the callee). Format depends on your SIP trunk:
# - Could be "sip:+15551234567@sip.twilio.com" or "tel:+15551234567" depending on provider expectations.
TARGET_PHONE = os.getenv("SIP_CALL_TO")

# ============================================================================
# AI ASSISTANT - define the agent's instructions and behavior
# ============================================================================
class Assistant(Agent):
    """
    Assistant is a subclass of livekit.agents.Agent.

    The Agent base class is an abstraction representing an LLM-driven conversational
    participant. When the AgentSession is started, the Agent is provided to the
    session.start(...) method. The session uses the Agent's instructions as the
    system prompt or guiding text when calling the LLM.

    Here we set `instructions` to influence how the LLM responds on the call.
    """
    def __init__(self):
        # Call the base class constructor with the instructions string.
        # The instruction text is used as the "system prompt" or high-level directive
        # for the LLM, telling it tone, length, and formatting expectations.
        super().__init__(
            instructions="""You are a helpful AI assistant on a phone call.
            Keep responses SHORT and conversational (1-3 sentences).
            No formatting, emojis, or special characters.
            Be friendly and professional."""
            # Explanation of each clause:
            # - "helpful AI assistant on a phone call": orients the model to speak conversationally.
            # - "Keep responses SHORT ...": constrains response length so the audio is short.
            # - "No formatting, emojis ...": ensures only plain natural text is produced (good for TTS).
            # - "Be friendly and professional.": sets tone.
        )

# ============================================================================
# AGENT ENTRYPOINT - this coroutine runs inside the agent worker process for a room/job
# ============================================================================
async def entrypoint(ctx: agents.JobContext):
    """
    Entrypoint is the asynchronous function the agent worker runs when assigned a job.

    Parameters:
    - ctx: agents.JobContext
      - Provided by the livekit agents runtime when the worker is handling a job/room.
      - Contains information about the room (ctx.room), methods to connect (ctx.connect),
        and helpers such as ctx.wait_for_participant() to wait for participants to join.

    Responsibilities of this function:
    - connect the worker to the room (subscribe to audio),
    - wait for the SIP participant (callee) to join,
    - initialize AgentSession with STT, LLM, TTS, VAD, and turn detection,
    - start the session and send an initial greeting.
    """
    # Print which room the worker is handling. ctx.room.name is the LiveKit room name.
    print(f"🎙️ Agent starting in room: {ctx.room.name}")

    # Connect to the LiveKit room as the agent participant.
    # - ctx.connect(...) returns when the worker has joined the room and can publish/subscribe.
    # - auto_subscribe=agents.AutoSubscribe.AUDIO_ONLY means the worker will subscribe only
    #   to audio tracks (not video or data), which is appropriate for voice-only calls.
    # - auto_subscribe is an enum provided by the SDK to request only what is necessary.
    await ctx.connect(auto_subscribe=agents.AutoSubscribe.AUDIO_ONLY)

    # Wait for the SIP participant (the callee) to appear in the room. This will block
    # until a participant joins (asynchronously). This function typically resolves when
    # LiveKit creates the room and puts the remote SIP participant inside the room after answer.
    print("⏳ Waiting for participant to connect...")
    participant = await ctx.wait_for_participant()
    # participant is an object representing the remote participant in the LiveKit room.
    # It typically contains fields like identity (string), name, tracks, etc.
    print(f"✅ Participant connected: {participant.identity}")

    # Initialize the AgentSession that wires together the external services.
    # AgentSession takes provider plugins for:
    # - stt: speech-to-text (transcribe incoming audio)
    # - llm: language model (generate agent text replies)
    # - tts: text-to-speech (synthesize agent text to audio)
    # - vad: voice activity detection (detect when someone is speaking)
    # - turn_detection: model to detect speaker turns (avoid talking over the human)
    #
    # Each plugin is instantiated with the credentials required by that external service.
    session = AgentSession(
        # deepgram.STT: streams or transcribes incoming audio to text using Deepgram's API.
        # The plugin wraps Deepgram's client to fit the AgentSession interface.
        stt=deepgram.STT(api_key=os.getenv("DEEPGRAM_API_KEY")),

        # google.LLM: wrapper that calls Google's Gemini LLM.
        # model: the model name string used by the plugin to choose which Gemini model to call.
        llm=google.LLM(
            model="gemini-2.0-flash-001",                # which Gemini model to use
            api_key=os.getenv("GEMINI_API_KEY")         # API key for Google Gemini (service account or API key)
        ),

        # aws.TTS: wrapper to use AWS Polly (or other AWS TTS) to synthesize voice audio.
        # voice: the name of a Polly voice (e.g., "Joanna", "Matthew", etc.)
        # region: AWS region for the Polly API
        # api_key/api_secret: credentials used to call AWS APIs (could be IAM user/API keys)
        tts=aws.TTS(
            voice="Joanna",
            region=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            api_key=os.getenv("AWS_API_KEY_ID"),
            api_secret=os.getenv("AWS_API_SECRET_KEY")
        ),

        # silero.VAD.load(): load a Silero voice activity detector instance.
        # VAD helps the system decide whether the callee is currently speaking.
        vad=silero.VAD.load(),

        # MultilingualModel is a turn detector: it attempts to mark boundaries where
        # speaker turns occur (so the agent can wait until the human finishes speaking).
        turn_detection=MultilingualModel(),
    )

    # Start the AgentSession.
    # - room: the LiveKit room object (ctx.room) where audio is flowing.
    # - agent: an instance of Assistant (our Agent subclass) which provides instructions
    #          and can optionally implement callbacks for advanced behavior.
    #
    # This call sets up the real-time pipeline:
    # - incoming audio -> STT -> transcriptions -> (optionally) context management ->
    #   llm -> text replies -> tts -> audio played back into the room.
    await session.start(room=ctx.room, agent=Assistant())
    print("🤖 Agent session started")

    # Sleep a short moment to give the audio graph time to stabilize (websocket tracks
    # to be fully negotiated, audio pipelines warmed up, etc.). This is heuristic.
    await asyncio.sleep(0.5)

    # Make the agent speak first by generating a reply. generate_reply triggers the LLM
    # with the provided instructions (a one-off override instruction for this reply).
    # - instructions: the text prompt used for this specific reply. This is merged with
    #   the agent's base instructions (set in Assistant).
    # The session will synthesize the LLM output with tts and publish it into the room.
    print("👋 Sending greeting...")
    await session.generate_reply(
        instructions="Greet the person warmly by saying: 'Hello! This is an AI assistant. How can I help you today?'"
        # Note: the instructions parameter is a short helper for this single reply.
        # The LLM will receive both the Agent's persistent instructions and this prompt.
    )
    print("✅ Greeting sent - conversation active")

# ============================================================================
# MAIN: create SIP trunk and place the outbound call (run when not running as agent)
# ============================================================================
async def main():
    """
    This function provisions a SIP outbound trunk in LiveKit (pointing at the Twilio/SIP provider)
    and then requests that LiveKit create a SIP participant (place the outbound call).

    Typical workflow:
    - Create trunk (only needed once in many setups; you can persist trunk_id and reuse)
    - Create SIP participant (this places the call using the trunk)
    - wait_until_answered=True is used to block until the call is answered, making coordination
      between the caller (this script) and the agent worker easier for demo/test environments.
    """
    # Create a LiveKit API client:
    # - LIVEKIT_URL: base URL for API
    # - LIVEKIT_API_KEY & LIVEKIT_API_SECRET: credentials for the API client
    lk_api = api.LiveKitAPI(LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)

    try:
        # Step 1: Create outbound SIP trunk on LiveKit that routes telephony calls to Twilio's SIP domain.
        # The request object is proto_sip.CreateSIPOutboundTrunkRequest which contains a `trunk` field.
        # proto_sip.SIPOutboundTrunkInfo holds the trunk configuration:
        # - name: friendly name for the trunk inside LiveKit
        # - address: the SIP domain/address of the upstream provider (TWILIO_SIP_DOMAIN)
        # - numbers: a list of phone numbers owned/used by the trunk (optional)
        # - auth_username/auth_password: if the upstream requires authentication for SIP, include them here.
        #
        # Note: Many deployments create the trunk once and reuse it. Creating a trunk repeatedly
        # may produce duplicates or may be rate-limited by your LiveKit server.
        print("📞 Creating SIP trunk...")
        trunk = await lk_api.sip.create_sip_outbound_trunk(
            create=proto_sip.CreateSIPOutboundTrunkRequest(
                trunk=proto_sip.SIPOutboundTrunkInfo(
                    name="Twilio Outbound",           # human-readable name for the trunk
                    address=TWILIO_SIP_DOMAIN,        # SIP provider domain or address
                    numbers=[TWILIO_PHONE_NUMBER],    # list of numbers associated with this trunk
                    auth_username=TWILIO_SIP_USERNAME,# SIP auth username (optional)
                    auth_password=TWILIO_SIP_PASSWORD,# SIP auth password (optional)
                )
            )
        )
        # trunk.sip_trunk_id: the identifier returned by LiveKit for the created trunk.
        # Use this id when creating SIP participants (placing calls).
        trunk_id = trunk.sip_trunk_id
        print(f"✅ Trunk created: {trunk_id}")

        # Step 2: Make outbound call by creating a SIP participant using the trunk_id.
        # proto_sip.CreateSIPParticipantRequest fields:
        # - sip_trunk_id: which trunk to use for this call
        # - sip_call_to: who to call (format must be compatible with your trunk/provider)
        # - room_name: name of the LiveKit room to create (the agent worker will join this room)
        # - participant_identity: identity string for the participant created by this API call
        # - participant_name: friendly display name for that participant
        # - krisp_enabled: enable AI-based noise suppression if supported
        # - wait_until_answered: if True, the API call will block until the call is answered;
        #                        when answered, LiveKit will create the room and add the SIP participant.
        print(f"📱 Calling {TARGET_PHONE}...")
        await lk_api.sip.create_sip_participant(
            create=proto_sip.CreateSIPParticipantRequest(
                sip_trunk_id=trunk_id,
                sip_call_to=TARGET_PHONE,
                room_name=f"call-{TARGET_PHONE.replace('+', '')}",
                participant_identity="ai-caller",
                participant_name="AI Assistant",
                krisp_enabled=True,        # request noise suppression for better audio quality
                wait_until_answered=True,  # block until the callee answers (useful for demos)
            )
        )
        # If create_sip_participant returns without exception and wait_until_answered was True,
        # the outbound call was answered and the room exists with the SIP participant inside it.
        print(f"✅ Call initiated! Agent will answer when picked up.")

    except Exception as e:
        # Catch-all error handling for demonstration. In production, use finer-grained handling
        # and do not print secrets or tracebacks to standard output in plain text.
        print(f"❌ Error: {e}")

    finally:
        # Close the API client HTTP connection pool gracefully.
        # This calls underlying aiohttp/HTTP client close methods if present.
        await lk_api.aclose()

# ============================================================================
# RUN: choose between placing a call (default) or running the agent worker
# ============================================================================
if __name__ == "__main__":
    # Standard Python trick to allow this file to be used as a script or imported as a module.
    import sys

    # If the first command-line argument is "agent", run the agent worker CLI.
    # This starts a long-running worker process which will accept jobs from LiveKit.
    if len(sys.argv) > 1 and sys.argv[1] == "agent":
        # Remove the 'agent' argument so the agents.cli.run_app receives a clean argv.
        sys.argv.pop(1)

        # agents.cli.run_app starts the worker process that listens for job assignments.
        # WorkerOptions(entrypoint_fnc=entrypoint) tells the worker to call our entrypoint(ctx)
        # for each assigned job/room. The worker manages lifecycle, reconnection, and job polling.
        agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
    else:
        # If not running in "agent" mode, run main() which creates the trunk and places the call.
        # asyncio.run schedules and runs the main() coroutine until completion.
        asyncio.run(main())