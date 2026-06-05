import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from pathlib import Path

# Import LangChain components
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage

# Load environment variables
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)

app = FastAPI(title="AI Services API")

# Lazy initialization placeholders
llm = None
structured_llm = None
interview_chain = None

# Define schemas for input and output
class ChatMessage(BaseModel):
    role: str
    content: Optional[str] = ""
    timestamp: Optional[str] = None

class ChatPayload(BaseModel):
    message: str
    history: List[ChatMessage]
    candidate_name: str
    candidate_email: str
    candidate_joined: str
    week_users_count: int
    week_users_list: List[str]
    course_name: str
    week_number: int
    week_title: str
    week_description: str
    interview_start_time: str
    elapsed_minutes: float

class InterviewResponse(BaseModel):
    reply: str = Field(
        description="The response or next question to ask the user. If the interview is finished, this should be a polite wrap-up message with the overall feedback."
    )
    finished: bool = Field(
        description="Set to true if the interview is complete (typically after asking 3-5 relevant questions and assessing the user's responses), false otherwise."
    )
    score: int = Field(
        description="The score (from 0 to 100) assessing the user's performance. Only provide a real score if finished is true, otherwise return 0."
    )

def get_interview_chain():
    """
    Lazily initialize and return the LangChain chain.
    This prevents startup validation errors if environment variables are not yet loaded.
    """
    global llm, structured_llm, interview_chain
    if interview_chain is None:
        # Re-load env just in case it was written after startup
        load_dotenv(dotenv_path=env_path)
        
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=500, 
                detail="Missing API Key. Please ensure GROQ_API_KEY is configured in your environment or ai_services/.env."
            )
        
        # Clean the key in case it was written with quotes or spaces in the .env file
        api_key = api_key.strip().strip('"').strip("'")
            
        llm = ChatGroq(
            model="llama-3.3-70b-versatile",
            groq_api_key=api_key,
            temperature=0.7
        )
        structured_llm = llm.with_structured_output(InterviewResponse)
        
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", "{system_instruction}"),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{user_message}")
        ])
        
        interview_chain = prompt_template | structured_llm
        
    return interview_chain

@app.post("/chat")
async def chat_endpoint(payload: ChatPayload):
    # Retrieve the LangChain chain (raises 500 if key is missing)
    chain = get_interview_chain()

    # Extract database fields directly from the payload
    user_name = payload.candidate_name
    user_email = payload.candidate_email
    user_joined = payload.candidate_joined
    week_users_count = payload.week_users_count
    week_users_list = payload.week_users_list

    course_name = payload.course_name
    week_number = payload.week_number
    week_title = payload.week_title
    week_description = payload.week_description

    elapsed_minutes = payload.elapsed_minutes
    interview_start_time = payload.interview_start_time

    # Prepare system instruction prompt
    system_instruction = f"""You are a professional and friendly AI Technical Interviewer.
Your goal is to conduct a technical interview for the candidate: {user_name} (Email: {user_email}).
They joined the platform on {user_joined}.
For registration week context: there were a total of {week_users_count} users registered during that specific week (including {', '.join(week_users_list[:5])}).

You are conducting this interview for the course: {course_name}
Specifically, for Week {week_number}: {week_title}.
Topic Description: {week_description}

Timing Context:
- Interview Start Time: {interview_start_time} UTC
- Elapsed Time: {elapsed_minutes:.1f} minutes
- Target duration of the interview: 30 minutes (0.5 hours). You must ask questions for 30 minutes before answering any candidate doubts.

IDE & Language Context:
- The candidate is using an integrated IDE that supports writing and submitting code in: Python, JavaScript, Go (Golang), Java, C, and C++.
- You should mention or allow the candidate to use any of these languages to solve practical/coding problems.

CRITICAL RULES:
1. FOCUS ONLY ON INTERVIEWING: Your primary job is to assess the candidate's understanding of the week's topic. Do NOT answer off-topic questions.
2. NO DOUBT SOLVING DURING INTERVIEW: If the user asks general questions or doubts during the interview (before 30 minutes have elapsed), you must politely refuse to answer. Explain to the user that you will address all of their doubts and questions *after* the interview is completed (once the 30 minutes are up).
3. QUESTION STRUCTURE:
   - You must ask a minimum of 8 to 10 theory questions ranging from basic to advanced difficulty.
   - You must ask exactly 3 practical/coding/problem-solving questions (1 easy and 2 intermediate difficulty).
   - Do not ask multiple questions at once. Ask them one by one, allowing the user to reply to each before asking the next.
   - Keep track of the question counts. Do not mark the interview as finished until both the minimum counts (8 theory + 3 practical questions) are satisfied.
4. CONTINUOUS ASSESSMENT & EXIT: Only stop when:
   - The user explicitly asks to "exit", "quit", "end", or "stop" the interview. If so, immediately set 'finished' to True, wrap up the interview, and provide their score.
   - The elapsed time is 30 minutes or more AND you have satisfied the minimum question structure (at least 8 theory and 3 practical questions). If 30 minutes have passed but the question count is not met, keep asking questions until the minimum count is satisfied.
5. OUT OF CONTEXT INPUTS: If the user types gibberish or attempts to divert the conversation to unrelated topics, politely guide them back to the interview questions.
6. EVALUATION: If 'finished' is True, evaluate the candidate's responses throughout the interview, provide brief constructive feedback, and calculate a score (0 to 100). If 'finished' is False, the 'score' MUST be 0.
"""

    # Format history for LangChain
    chat_history = []
    for msg in payload.history:
        content = msg.content or ""
        if msg.role == "user":
            chat_history.append(HumanMessage(content=content))
        elif msg.role == "assistant":
            chat_history.append(AIMessage(content=content))

    try:
        # Run LangChain invocation
        response = chain.invoke({
            "system_instruction": system_instruction,
            "chat_history": chat_history,
            "user_message": payload.message
        })
        
        return {
            "reply": response.reply,
            "finished": response.finished,
            "score": response.score
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate AI response: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("interview:app", host="127.0.0.1", port=8001, reload=True)
