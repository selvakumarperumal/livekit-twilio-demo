import asyncio
from livekit import api
from livekit.api.twirp_client import TwirpError
from livekit.protocol import sip as proto_sip
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv("./.env")

class Settings(BaseSettings):
    LIVEKIT_URL: str
    LIVEKIT_API_KEY: str
    LIVEKIT_API_SECRET: str
    SIP_TRUNK_ID: str
    SIP_CALL_TO: str

async def make_outbound_call():
    settings = Settings()
    lk_api = api.LiveKitAPI(
        url=settings.LIVEKIT_URL,
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET
    )
    
    try:
        # Replace with your actual trunk ID from Step 1
        trunk_id = settings.SIP_TRUNK_ID  # TODO: Replace this!
        
        # Make the call
        participant = await lk_api.sip.create_sip_participant(
            create=proto_sip.CreateSIPParticipantRequest(
                sip_trunk_id=trunk_id,
                
                # The phone number you want to call (include country code)
                sip_call_to=settings.SIP_CALL_TO,  # TODO: Replace with test number
                
                # LiveKit room where the call will happen
                room_name="outbound-test-call",
                
                # Identity for this participant
                participant_identity="outbound-caller",
                participant_name="Test Caller",
                
                # Optional: Enable noise cancellation
                krisp_enabled=True,
                
                # Wait for the call to be answered before joining room
                wait_until_answered=True,
            )
        )
        
        print(f"✅ Call initiated!")
        print(f"📞 SIP Call ID: {participant.sip_call_id}")
        print(f"🆔 Participant ID: {participant.participant_id}")
        print(f"📍 Room: {participant.room_name}")
        
    except TwirpError as e:
        print(f"❌ Call failed!")
        print(f"Error code: {e.code}")
        print(f"Message: {e.message}")
        if e.metadata:
            sip_status = e.metadata.get('sip_status')
            sip_code = e.metadata.get('sip_status_code')
            if sip_status and sip_code:
                print(f"SIP Status: {sip_code} - {sip_status}")
                print(f"\n💡 SIP status '{sip_code}' typically means:")
                if sip_code == '486':
                    print("   - The phone is busy or rejecting the call")
                    print("   - Try calling a different number")
                    print("   - Check if the number can receive calls")
    except Exception as e:
        print(f"❌ Unexpected error: {type(e).__name__}: {e}")
    finally:
        await lk_api.aclose()

if __name__ == "__main__":
    asyncio.run(make_outbound_call())