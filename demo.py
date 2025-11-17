# ============================================================================
# IMPORTS - Required Libraries
# ============================================================================

import asyncio
# asyncio: Python's built-in library for writing asynchronous code
# Allows running async functions (functions that can pause and resume)
# Needed because LiveKit API operations are asynchronous (non-blocking)

from livekit import api
# api: LiveKit's main API module
# Provides LiveKitAPI class to interact with LiveKit server
# Used to manage rooms, participants, SIP trunks, etc.

from livekit.protocol import sip as proto_sip
# proto_sip: Protocol buffer definitions for SIP operations
# Contains data structures (classes) for SIP trunk configuration
# These are strongly-typed objects that match LiveKit's API schema
from dotenv import load_dotenv
# load_dotenv: Function to load environment variables from a .env file
# Helps manage sensitive configuration (API keys, secrets) outside code
load_dotenv("./.env")
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    LIVEKIT_URL: str
    LIVEKIT_API_KEY: str
    LIVEKIT_API_SECRET: str
    TWILIO_SIP_URI: str
    Number: str
    TWILIO_SIP_USERNAME: str
    TWILIO_SIP_PASSWORD: str


# ============================================================================
# MAIN FUNCTION - Create Outbound SIP Trunk
# ============================================================================

async def create_twilio_outbound_trunk():
    settings = Settings()
    # async def: Declares an asynchronous function
    # Must be called with 'await' or through asyncio.run()
    # Allows the function to use 'await' for non-blocking operations
    
    """
    Creates a SIP outbound trunk in LiveKit that connects to Twilio.
    This trunk allows LiveKit to make outbound phone calls through Twilio's network.
    
    Flow:
    1. Authenticate with LiveKit Cloud
    2. Configure trunk with Twilio's SIP domain
    3. Set authentication credentials (must match Twilio's credential list)
    4. Return trunk ID for making calls
    """
    
    
    # ========================================================================
    # STEP 1: Initialize LiveKit API Client
    # ========================================================================
    
    lk_api = api.LiveKitAPI(
        # Creates an instance of LiveKitAPI to communicate with LiveKit server
        # This object provides methods for all LiveKit operations
        
        url=settings.LIVEKIT_URL,
        # url: WebSocket Secure (wss://) endpoint for your LiveKit project
        # Format: wss://<your-project-id>.livekit.cloud
        # "voice-agent-j2i5jp1v" is your unique project identifier
        # This is where all API requests will be sent
        
        api_key=settings.LIVEKIT_API_KEY,
        # api_key: Public identifier for API authentication
        # Format: Usually starts with "API" followed by random characters
        # Not secret, but used in combination with api_secret
        # Found in LiveKit Cloud Dashboard → Settings → API Keys
        
        api_secret=settings.LIVEKIT_API_SECRET,
        # api_secret: Private key for API authentication
        # THIS IS SENSITIVE - Keep it secret, never commit to version control
        # Used to sign/verify requests (like a password)
        # Together with api_key, proves you have permission to use the API
    )
    
    
    # ========================================================================
    # STEP 2: Create SIP Outbound Trunk Configuration
    # ========================================================================
    
    trunk = await lk_api.sip.create_sip_outbound_trunk(
        # await: Pauses execution until the API call completes
        # lk_api.sip: Access SIP-specific methods on the API client
        # create_sip_outbound_trunk(): Method to register a new outbound trunk
        # Returns: SIPOutboundTrunkInfo object with trunk details (including ID)
        
        create=proto_sip.CreateSIPOutboundTrunkRequest(
            # CreateSIPOutboundTrunkRequest: Wrapper object for the API request
            # This is a protocol buffer message that structures the request
            # Ensures type safety and proper serialization
            
            trunk=proto_sip.SIPOutboundTrunkInfo(
                # SIPOutboundTrunkInfo: Contains all trunk configuration details
                # This object defines HOW LiveKit connects to Twilio
                
                
                # ------------------------------------------------------------
                # TRUNK IDENTIFICATION
                # ------------------------------------------------------------
                
                name="Twilio Outbound",
                # name: Human-readable identifier for this trunk
                # Used in LiveKit Dashboard and logs
                # Can be anything descriptive (e.g., "Production Twilio", "Dev Trunk")
                
                
                # ------------------------------------------------------------
                # TWILIO SIP ENDPOINT
                # ------------------------------------------------------------
                
                address=settings.TWILIO_SIP_URI,
                # address: Twilio's SIP domain for your trunk
                # This is WHERE LiveKit will send call requests
                # 
                # Format: <your-trunk-name>.pstn.twilio.com
                # 
                # How to find this:
                # 1. Go to Twilio Console → Elastic SIP Trunking → Your Trunk
                # 2. Look at the top or "General" section
                # 3. You'll see "SIP URI: sip:livekit-twilio-demo-1.pstn.twilio.com"
                # 4. Use the domain part WITHOUT "sip:" prefix
                # 
                # What it does:
                # - When you make a call, LiveKit sends SIP INVITE to this address
                # - Twilio receives it, authenticates, then routes to PSTN
                
                
                # ------------------------------------------------------------
                # CALLER ID (FROM NUMBER)
                # ------------------------------------------------------------
                
                numbers=[settings.Number],
                # numbers: List of phone numbers associated with this trunk
                # This is the "Caller ID" / "From" number shown to recipients
                # 
                # Format: E.164 format (+ country_code + number)
                # Example: +1 504 608 0604
                #   +1   = USA country code
                #   504  = Area code (New Orleans)
                #   608-0604 = Local number
                # 
                # Requirements:
                # - Must be a phone number you own in Twilio
                # - Must be assigned to your SIP trunk in Twilio Console
                # - Can include multiple numbers (e.g., ["+15046080604", "+15551234567"])
                # 
                # What it does:
                # - When someone receives your call, this is what they see
                # - Twilio verifies you own this number before allowing calls
                
                
                # ------------------------------------------------------------
                # AUTHENTICATION CREDENTIALS
                # ------------------------------------------------------------
                
                auth_username=settings.TWILIO_SIP_USERNAME,
                # auth_username: Username for SIP authentication
                # This MUST match the username in your Twilio Credential List
                # 
                # Where this comes from:
                # 1. Twilio Console → Your Trunk → Termination tab
                # 2. Under "Credential Lists", click your list (e.g., "livekit-twilio-demo")
                # 3. View credentials → Username field
                # 
                # What it does:
                # - When LiveKit makes a call, Twilio challenges with: "Who are you?"
                # - LiveKit responds with this username
                # - Twilio checks if this username exists in the credential list
                # - If username + password match, call is allowed
                # 
                # Security:
                # - Acts like a "user account" for your trunk
                # - Prevents unauthorized use of your Twilio trunk
                
                auth_password=settings.TWILIO_SIP_PASSWORD,
                # auth_password: Password for SIP authentication
                # This MUST match the password in your Twilio Credential List
                # 
                # Where this comes from:
                # 1. Same place as username (Twilio → Trunk → Termination → Credentials)
                # 2. This is what YOU set when creating the credential
                # 
                # What it does:
                # - Twilio challenges: "Prove you're authorized"
                # - LiveKit sends this password (encrypted via SIP Digest Auth)
                # - Twilio verifies: username + password combination
                # - If correct, call proceeds; if wrong, call fails with 401/403 error
                # 
                # Security:
                # - THIS IS SENSITIVE - Keep secret!
                # - Use environment variables in production:
                #   auth_password=os.getenv("TWILIO_SIP_PASSWORD")
                # - Twilio never sees this in plaintext (hashed via SIP protocol)
                # 
                # Best practices:
                # - Use strong passwords (mix of letters, numbers, symbols)
                # - Don't use the same password as your Twilio account
                # - Rotate periodically
                
                
                # ------------------------------------------------------------
                # OPTIONAL CONFIGURATIONS (can add below)
                # ------------------------------------------------------------
                
                # metadata="key1=value1,key2=value2",
                # metadata: Custom key-value pairs for your reference
                # Not used by LiveKit/Twilio, just for your tracking
                
                # krisp_enabled=True,
                # krisp_enabled: Enable AI-powered noise cancellation
                # Reduces background noise on calls (default: False)
                
                # headers={"X-Custom-Header": "value"},
                # headers: Custom SIP headers to include in INVITE messages
                # Useful for passing data to Twilio or downstream systems
            )
        )
    )
    
    
    # ========================================================================
    # STEP 3: Output Result and Cleanup
    # ========================================================================
    
    print(f"✅ Outbound trunk created: {trunk.sip_trunk_id}")
    # trunk: The returned SIPOutboundTrunkInfo object
    # trunk.sip_trunk_id: Unique identifier (UUID) for this trunk
    #   Example: "ST_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
    # 
    # What to do with this ID:
    # - SAVE IT! You need it to make outbound calls
    # - Store in database or config file
    # - Use it in create_sip_participant() calls
    # 
    # Example usage:
    #   trunk_id = "ST_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
    #   await lk_api.sip.create_sip_participant(
    #       sip_trunk_id=trunk_id,
    #       sip_call_to="+15551234567",
    #       room_name="my-call-room"
    #   )
    
    await lk_api.aclose()
    # aclose(): Gracefully closes the API client connection
    # Important to avoid resource leaks (open websockets, pending requests)
    # Always call this when done with lk_api
    # 
    # Note: In production with long-running services, create one lk_api
    # instance and reuse it, closing only on shutdown


# ============================================================================
# SCRIPT ENTRY POINT
# ============================================================================

asyncio.run(create_twilio_outbound_trunk())
# asyncio.run(): Executes an async function from synchronous code
# This is the "entry point" that starts the async event loop
# 
# What happens:
# 1. Creates a new event loop
# 2. Runs create_twilio_outbound_trunk() to completion
# 3. Closes the event loop
# 
# Alternative for interactive/production use:
#   async def main():
#       await create_twilio_outbound_trunk()
#       # Do other async operations...
#   
#   if __name__ == "__main__":
#       asyncio.run(main())