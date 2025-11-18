"""
LiveKit AI Agent - Inbound Phone Calls
Handles incoming phone calls via Twilio SIP trunk

Usage:
  python inbound_agent.py setup    # Create inbound trunk & dispatch rule
  python inbound_agent.py agent    # Start agent worker
"""

import asyncio
import os
import sys
from dotenv import load_dotenv
from livekit import agents, api
from livekit.agents import AgentSession, Agent
from livekit.plugins import aws, google, deepgram, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

load_dotenv()

LIVEKIT_URL = os.getenv("LIVEKIT_URL")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")


# ============================================================================
# AGENT DEFINITION
# ============================================================================
class Assistant(Agent):
    def __init__(self):
        super().__init__(
            instructions="""You are a helpful AI assistant on a phone call.
            Keep responses SHORT (1-2 sentences). Be conversational and friendly.
            No emojis or special characters - just natural speech."""
        )


# ============================================================================
# AGENT ENTRYPOINT
# ============================================================================
async def entrypoint(ctx: agents.JobContext):
    """Handle incoming phone call with AI voice agent"""
    
    print(f"🎙️ Agent ready in room: {ctx.room.name}")
    
    # Connect to the room
    await ctx.connect()
    
    # Wait for SIP participant (caller) to join
    participant = await ctx.wait_for_participant()
    print(f"📞 Call connected from: {participant.identity}")
    
    # Create AI agent session
    session = AgentSession(
        stt=deepgram.STT(
            api_key=os.getenv("DEEPGRAM_API_KEY"),
            language="en",
        ),
        llm=google.LLM(
            model="gemini-2.0-flash-001",
            api_key=os.getenv("GEMINI_API_KEY"),
            temperature=0.8,
        ),
        tts=aws.TTS(
            voice="Joanna",
            region=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            api_key=os.getenv("AWS_API_KEY_ID"),
            api_secret=os.getenv("AWS_API_SECRET_KEY"),
        ),
        vad=silero.VAD.load(),
        turn_detection=MultilingualModel(),
    )
    
    # Start the session
    await session.start(room=ctx.room, agent=Assistant())
    
    # Greet the caller
    await session.generate_reply(
        instructions="Greet the user and offer your assistance."
    )


# ============================================================================
# SETUP COMMAND
# ============================================================================
async def setup_inbound():
    """Create inbound trunk and dispatch rule (run once)"""
    
    lk_api = api.LiveKitAPI(LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
    
    try:
        print("🔧 Setting up inbound call handling...")
        
        # Step 1: Create inbound trunk
        print("\n📥 Creating inbound trunk...")
        trunk = await lk_api.sip.create_sip_inbound_trunk(
            api.CreateSIPInboundTrunkRequest(
                trunk=api.SIPInboundTrunkInfo(
                    name="Twilio Inbound",
                    numbers=[TWILIO_PHONE_NUMBER],
                )
            )
        )
        trunk_id = trunk.sip_trunk_id
        print(f"✅ Trunk created: {trunk_id}")
        
        # Step 2: Create dispatch rule
        print("\n🎯 Creating dispatch rule...")
        dispatch_rule = await lk_api.sip.create_sip_dispatch_rule(
            api.CreateSIPDispatchRuleRequest(
                dispatch_rule=api.SIPDispatchRuleInfo(
                    name="Route to AI Agent",
                    trunk_ids=[trunk_id],
                    rule=api.SIPDispatchRule(
                        dispatch_rule_individual=api.SIPDispatchRuleIndividual(
                            room_prefix="call-"
                        )
                    ),
                    hide_phone_number=False,
                )
            )
        )
        print(f"✅ Dispatch rule created: {dispatch_rule.sip_dispatch_rule_id}")
        
        print("\n✅ Setup complete!")
        print("\n📞 Next: python inbound_agent.py agent")
        
    except Exception as e:
        if "already exists" in str(e).lower():
            print(f"✅ Already configured (trunk/rule exists)")
        else:
            print(f"❌ Error: {e}")
    
    finally:
        await lk_api.aclose()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python inbound_agent.py setup    # Setup once")
        print("  python inbound_agent.py agent    # Run to answer calls")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "setup":
        asyncio.run(setup_inbound())
    elif command == "agent":
        sys.argv.pop(1)
        agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
    else:
        print(f"❌ Unknown command: {command}")