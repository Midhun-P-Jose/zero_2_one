import os
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Import LangChain components
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage

# Load environment variables
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)

# Resolve DB path
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "db.sqlite3"

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
    week_title: Optional[str] = None
    user_id: Optional[int] = None
    week_id: Optional[int] = None

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

def get_user_and_week_users(user_id: int):
    """
    Query Django auth_user and find other users who registered in the same calendar week of the same year.
    """
    if not DB_PATH.exists():
        return None, 0, []
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 1. Get candidate info
        cursor.execute("""
            SELECT id, username, first_name, email, date_joined 
            FROM auth_user 
            WHERE id = ?
        """, (user_id,))
        user_row = cursor.fetchone()
        if not user_row:
            conn.close()
            return None, 0, []
            
        user_data = dict(user_row)
        date_joined_str = user_data["date_joined"]
        
        # 2. Get all users registered in the same calendar week of the same year
        cursor.execute("""
            SELECT id, username, first_name, email, date_joined 
            FROM auth_user 
            WHERE strftime('%Y-%W', date_joined) = strftime('%Y-%W', ?)
        """, (date_joined_str,))
        week_users_rows = cursor.fetchall()
        week_users = [dict(row) for row in week_users_rows]
        
        conn.close()
        return user_data, len(week_users), week_users
    except Exception as e:
        print(f"Error querying database: {e}")
        return None, 0, []

def get_course_week_data(week_id: int):
    """
    Query curriculum_courseweek and curriculum_course to get details of the current week.
    """
    if not DB_PATH.exists():
        return None
        
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT cw.week_number, cw.title as week_title, cw.description as week_desc, 
                   c.name as course_name, c.description as course_desc
            FROM curriculum_courseweek cw
            JOIN curriculum_course c ON cw.course_id = c.id
            WHERE cw.id = ?
        """, (week_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        print(f"Error querying course week: {e}")
        return None

def get_interview_created_at(user_id: int, week_id: int):
    """
    Get the created_at timestamp for the specific user and week interview session.
    """
    if not DB_PATH.exists():
        return None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT created_at 
            FROM curriculum_interview_questions 
            WHERE user_id = ? AND week_id = ?
        """, (user_id, week_id))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        print(f"Error querying interview created_at: {e}")
        return None

def get_elapsed_minutes(created_at_str: str) -> float:
    """
    Calculate the elapsed minutes since the interview session was created.
    """
    if not created_at_str:
        return 0.0
    try:
        from datetime import datetime
        # Strip timezone offsets (e.g. +00:00 or Z) for isoformat parsing
        clean_str = created_at_str.replace('Z', '')
        if '+' in clean_str:
            clean_str = clean_str.split('+')[0]
        dt = datetime.fromisoformat(clean_str)
        
        # Calculate difference from UTC now (since Django stores datetimes in UTC in sqlite)
        now = datetime.utcnow()
        diff_seconds = (now - dt).total_seconds()
        return max(0.0, diff_seconds / 60.0)
    except Exception as e:
        print(f"Error calculating elapsed time: {e}")
        return 0.0

@app.post("/chat")
async def chat_endpoint(payload: ChatPayload):
    # Retrieve the LangChain chain (raises 500 if key is missing)
    chain = get_interview_chain()

    # Determine candidate details
    user_name = "Candidate"
    user_email = "Not provided"
    user_joined = "Unknown"
    week_users_count = 0
    week_users_list = []
    
    if payload.user_id:
        user_data, count, users = get_user_and_week_users(payload.user_id)
        if user_data:
            user_name = user_data.get("first_name") or user_data.get("username") or "Candidate"
            user_email = user_data.get("email") or "Not provided"
            user_joined = user_data.get("date_joined") or "Unknown"
            week_users_count = count
            week_users_list = []
            for u in users:
                name = u.get("first_name") or u.get("username") or u.get("email")
                if name:
                    week_users_list.append(str(name))

    # Determine course and week details
    course_name = "Selected Course"
    week_number = 1
    week_title = payload.week_title or "Weekly Assessment"
    week_description = "General assessment"
    
    if payload.week_id:
        week_data = get_course_week_data(payload.week_id)
        if week_data:
            course_name = week_data.get("course_name") or course_name
            week_number = week_data.get("week_number") or week_number
            week_title = week_data.get("week_title") or week_title
            week_description = week_data.get("week_desc") or week_description

    # Determine elapsed time for the 30-minute interview requirement
    elapsed_minutes = 0.0
    interview_start_time = "Unknown"
    if payload.user_id and payload.week_id:
        created_at_str = get_interview_created_at(payload.user_id, payload.week_id)
        if created_at_str:
            interview_start_time = created_at_str
            elapsed_minutes = get_elapsed_minutes(created_at_str)

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

CRITICAL RULES:
1. FOCUS ONLY ON INTERVIEWING: Your primary job is to assess the candidate's understanding of the week's topic. Do NOT answer off-topic questions.
2. NO DOUBT SOLVING DURING INTERVIEW: If the user asks general questions or doubts during the interview (before 30 minutes have elapsed), you must politely refuse to answer. Explain to the user that you will address all of their doubts and questions *after* the interview is completed (once the 30 minutes are up).
3. CONTINUOUS ASSESSMENT: Keep asking relevant technical questions one by one. Do not ask multiple questions at once. Only stop when:
   - The user explicitly asks to "exit", "quit", "end", or "stop" the interview. If so, immediately set 'finished' to True, wrap up the interview, and provide their score.
   - The elapsed time is 30 minutes or more. Once elapsed time is >= 30.0 minutes, you may finish the interview, set 'finished' to True, provide their score, and offer to answer any of their doubts.
4. OUT OF CONTEXT INPUTS: If the user types gibberish or attempts to divert the conversation to unrelated topics, politely guide them back to the interview questions.
5. EVALUATION: If 'finished' is True, evaluate the candidate's responses throughout the interview, provide brief constructive feedback, and calculate a score (0 to 100). If 'finished' is False, the 'score' MUST be 0.
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
    uvicorn.run("main:app", host="127.0.0.1", port=8001, reload=True)
