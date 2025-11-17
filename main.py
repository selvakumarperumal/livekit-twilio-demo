from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions
from livekit.plugins import aws, google, deepgram, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel
import os

load_dotenv("./.env", override=True)


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""You are a helpful voice AI assistant.
            You eagerly assist users with their questions by providing information from your extensive knowledge.
            Your responses are concise, to the point, and without any complex formatting or punctuation including emojis, asterisks, or other symbols.
            You are curious, friendly, and have a sense of humor.""",
        )


async def entrypoint(ctx: agents.JobContext):

    stt = deepgram.STT(api_key=os.getenv("DEEPGRAM_API_KEY"))
    tts = aws.TTS(
        voice="Joanna",
        region=os.getenv("AWS_DEFAULT_REGION"),
        api_key=os.getenv("AWS_API_KEY_ID"),
        api_secret=os.getenv("AWS_API_SECRET_KEY")
    )
    llm = google.LLM(model="gemini-2.0-flash-001", api_key=os.getenv("GEMINI_API_KEY"))
    
    session = AgentSession(
        stt=stt,
        llm=llm,
        tts=tts,
        vad=silero.VAD.load(),
        turn_detection=MultilingualModel(),
    )

    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_input_options=RoomInputOptions(
        ),
    )

    await session.generate_reply(
        instructions="Greet the user and offer your assistance."
    )


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))