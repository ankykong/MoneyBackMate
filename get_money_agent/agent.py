import os
import sys

from dotenv import load_dotenv
from loguru import logger

from utils import set_prompt
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer, VADParams
from pipecat.frames.frames import EndTaskFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.llm_service import LLMService
from pipecat.services.google .llm import GoogleLLMService
from pipecat.transports.services.daily import DailyParams, DailyTransport


class Agent:
    def __init__(
            self,
            phone_number: str,
            company_name: str,
            customer_name: str,
            account_number: str,
            desired_resolution: str,
            product_or_service: str,
            issue_description: str,
            proof: str):
        self.phone_number = phone_number
        self.company_name = company_name
        self.customer_name = customer_name
        self.account_number = account_number
        self.desired_resolution = desired_resolution
        self.product_or_service = product_or_service
        self.issue_description = issue_description
        self.proof = proof

        load_dotenv(override=True)

        logger.remove(0)
        logger.add(sys.stderr, level="DEBUG")

        self.daily_api_key = os.getenv("DAILY_API_KEY", "")
        self.daily_api_url = os.getenv("DAILY_API_URL", "https://api.daily.co/v1")

    async def main(
        self,
        room_url: str,
        token: str,
    ):

        # ------------ TRANSPORT SETUP ------------

        transport_params = DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            camera_out_enabled=False,
            transcription_enabled=True,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(
                    stop_secs=0.2,
                    start_secs=0.2,
                    confidence=0.4
                )
            ),
        ),

        # Initialize transport with Daily
        transport = DailyTransport(
            room_url,
            token,
            "Get Money Bot",
            transport_params,
        )

        # Initialize TTS
        tts = ElevenLabsTTSService(
            api_key=os.getenv("ELEVEN_LABS_API_KEY", ""),
            voice_id="b7d50908-b17c-442d-ad8d-810c63997ed9",  # Use Helpful Woman voice by default
        )

        # ------------ FUNCTION DEFINITIONS ------------

        async def terminate_call(
            function_name, tool_call_id, args, llm: LLMService, context, result_callback
        ):
            """Function the bot can call to terminate the call upon completion of a voicemail message."""
            await llm.queue_frame(EndTaskFrame(), FrameDirection.UPSTREAM)

        # Define function schemas for tools
        terminate_call_function = FunctionSchema(
            name="terminate_call",
            description="Call this function to terminate the call.",
            properties={},
            required=[],
        )

        # Create tools schema
        tools = ToolsSchema(standard_tools=[terminate_call_function])

        # ------------ LLM AND CONTEXT SETUP ------------

        # Initialize LLM
        llm = GoogleLLMService(api_key=os.getenv("GOOGLE_API_KEY"), model="gemini-2.0-flash")

        # Register functions with the LLM
        llm.register_function("terminate_call", terminate_call)

        system_prompt = set_prompt(
            customer_name=self.customer_name,
            company_name=self.company_name,
            desired_resolution=self.desired_resolution,
            account_number=self.account_number,
            product_or_service=self.product_or_service,
            issue_description=self.issue_description,
            proof=self.proof
        )

        # Create system message and initialize messages list
        messages = [{"role": "system", "content": system_prompt}]

        # Initialize LLM context and aggregator
        context = OpenAILLMContext(messages, tools)
        context_aggregator = llm.create_context_aggregator(context)

        # ------------ PIPELINE SETUP ------------

        # Build pipeline
        pipeline = Pipeline(
            [
                transport.input(),  # Transport user input
                context_aggregator.user(),  # User responses
                llm,  # LLM
                tts,  # TTS
                transport.output(),  # Transport bot output
                context_aggregator.assistant(),  # Assistant spoken responses
            ]
        )

        # Create pipeline task
        task = PipelineTask(pipeline, params=PipelineParams(allow_interruptions=True))

        # ------------ EVENT HANDLERS ------------

        @transport.event_handler("on_joined")
        async def on_joined(transport, data):
            # Start dialout
            logger.debug("Dialout settings detected; starting dialout")
            await transport.start_dialout({"phoneNumber": self.phone_number})

        @transport.event_handler("on_dialout_connected")
        async def on_dialout_connected(transport, data):
            logger.debug(f"Dial-out connected: {data}")

        @transport.event_handler("on_dialout_answered")
        async def on_dialout_answered(transport, data):
            logger.debug(f"Dial-out answered: {data}")
            # Automatically start capturing transcription for the participant
            await transport.capture_participant_transcription(data["sessionId"])
            # The bot will wait to hear the user before the bot speaks

        @transport.event_handler("on_first_participant_joined")
        async def on_first_participant_joined(transport, participant):
            logger.debug(f"First participant joined: {participant['id']}")
            await transport.capture_participant_transcription(participant["id"])
            # The bot will wait to hear the user before the bot speaks

        @transport.event_handler("on_participant_left")
        async def on_participant_left(transport, participant, reason):
            logger.debug(f"Participant left: {participant}, reason: {reason}")
            await task.cancel()

        # ------------ RUN PIPELINE ------------

        runner = PipelineRunner()
        await runner.run(task)
