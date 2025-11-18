"""
Simple AI Voice Agent for Outbound Calls via Twilio + LiveKit
Usage: python voice_agent.py
"""

import asyncio
import os
from dotenv import load_dotenv
from livekit import agents, rtc, api
from livekit.agents import AgentSession, Agent
from livekit.plugins import aws, google, deepgram, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from livekit.protocol import sip as proto_sip

load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================
LIVEKIT_URL = os.getenv("LIVEKIT_URL")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")

TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
TWILIO_SIP_DOMAIN = os.getenv("TWILIO_SIP_DOMAIN")
TWILIO_SIP_USERNAME = os.getenv("TWILIO_SIP_USERNAME")
TWILIO_SIP_PASSWORD = os.getenv("TWILIO_SIP_PASSWORD")

# Target phone number to call (CHANGE THIS!)
TARGET_PHONE = os.getenv("SIP_CALL_TO")


# ============================================================================
# AI ASSISTANT
# ============================================================================
class Assistant(Agent):
    def __init__(self):
        super().__init__(
            instructions="""You are a helpful AI assistant on a phone call.
            Keep responses SHORT and conversational (1-3 sentences).
            No formatting, emojis, or special characters.
            Be friendly and professional."""
        )


# ============================================================================
# AGENT ENTRYPOINT (Handles the call)
# ============================================================================
async def entrypoint(ctx: agents.JobContext):
    """Handle outbound call with AI agent"""
    
    print(f"🎙️ Agent starting in room: {ctx.room.name}")
    
    # Connect to room
    await ctx.connect(auto_subscribe=agents.AutoSubscribe.AUDIO_ONLY)
    
    # Wait for SIP participant (caller) to join
    print("⏳ Waiting for participant to connect...")
    participant = await ctx.wait_for_participant()
    print(f"✅ Participant connected: {participant.identity}")
    
    # Initialize AI services
    session = AgentSession(
        stt=deepgram.STT(api_key=os.getenv("DEEPGRAM_API_KEY")),
        llm=google.LLM(model="gemini-2.0-flash-001", api_key=os.getenv("GEMINI_API_KEY")),
        tts=aws.TTS(
            voice="Joanna",
            region=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            api_key=os.getenv("AWS_API_KEY_ID"),
            api_secret=os.getenv("AWS_API_SECRET_KEY")
        ),
        vad=silero.VAD.load(),
        turn_detection=MultilingualModel(),
    )
    
    # Start agent session
    await session.start(room=ctx.room, agent=Assistant())
    print("🤖 Agent session started")
    
    # Wait a moment for audio to be ready
    await asyncio.sleep(0.5)
    
    # Make the agent speak first
    print("👋 Sending greeting...")
    await session.generate_reply(
        instructions="Greet the person warmly by saying: 'Hello! This is an AI assistant. How can I help you today?'"
    )
    print("✅ Greeting sent - conversation active")


# ============================================================================
# MAIN: Setup trunk and make call
# ============================================================================
async def main():
    """Create trunk and make outbound call"""
    
    lk_api = api.LiveKitAPI(LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
    
    try:
        # Step 1: Create outbound trunk (run once, then comment out)
        print("📞 Creating SIP trunk...")
        trunk = await lk_api.sip.create_sip_outbound_trunk(
            create=proto_sip.CreateSIPOutboundTrunkRequest(
                trunk=proto_sip.SIPOutboundTrunkInfo(
                    name="Twilio Outbound",
                    address=TWILIO_SIP_DOMAIN,
                    numbers=[TWILIO_PHONE_NUMBER],
                    auth_username=TWILIO_SIP_USERNAME,
                    auth_password=TWILIO_SIP_PASSWORD,
                )
            )
        )
        trunk_id = trunk.sip_trunk_id
        print(f"✅ Trunk created: {trunk_id}")
        
        # Step 2: Make outbound call
        print(f"📱 Calling {TARGET_PHONE}...")
        await lk_api.sip.create_sip_participant(
            create=proto_sip.CreateSIPParticipantRequest(
                sip_trunk_id=trunk_id,
                sip_call_to=TARGET_PHONE,
                room_name=f"call-{TARGET_PHONE.replace('+', '')}",
                participant_identity="ai-caller",
                participant_name="AI Assistant",
                krisp_enabled=True,
                wait_until_answered=True,
            )
        )
        print(f"✅ Call initiated! Agent will answer when picked up.")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await lk_api.aclose()


# ============================================================================
# RUN
# ============================================================================
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "agent":
        # Run as agent worker: python outbound_agent.py agent
        # Remove 'agent' from sys.argv so cli.run_app works correctly
        sys.argv.pop(1)
        agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
    else:
        # Run to make call: python outbound_agent.py
        asyncio.run(main())