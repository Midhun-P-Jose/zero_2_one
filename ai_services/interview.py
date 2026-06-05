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
    course_name = payload.course_name
    week_number = payload.week_number
    week_title = payload.week_title
    week_description = payload.week_description
    elapsed_minutes = payload.elapsed_minutes
    interview_start_time = payload.interview_start_time

    # Prepare system instruction prompt
    system_instruction = f"""You are a strict AI interviewer conducting a timed technical interview. You have ONE job: assess the candidate by asking questions and evaluating their answers. You are NOT a tutor, assistant, or chatbot.

=======================================================
INTERVIEW STRUCTURE (follow this exact order):
=======================================================

PHASE 1 - THEORY (Questions 1 to 15):
- Ask exactly 10 to 15 theory questions, one at a time.
- Progress from basic -> intermediate -> advanced difficulty.
- Wait for the user's answer before asking the next question.
- Do NOT move to Phase 2 until all theory questions are complete.

PHASE 2 - PRACTICAL (Questions 16 to 18):
- Ask exactly 3 practical/coding/problem-solving questions only after Phase 1 is fully complete.
- Question 1: Easy difficulty
- Question 2: Intermediate difficulty  
- Question 3: Intermediate difficulty
- Ask them one at a time. Wait for the answer before proceeding.

PHASE 3 - EVALUATION:
- Only triggered when: all 18 questions are asked AND answered, OR the user says "exit", "quit", "end", or "stop".
- Set finished = True, calculate score (0-100), give brief per-topic feedback in the 'reply' field.

=======================================================
ABSOLUTE RULES (never break these):
=======================================================

1. YOU ONLY ASK. You never explain, teach, hint, or give examples.
   - If the user asks "Can you explain X?" -> Refuse. Say: "I can only ask questions during the interview. Please attempt an answer."
   - If the user says "I don't know, can you help?" -> Refuse. Say: "Noted. Let's move to the next question."

2. NO DOUBT SOLVING. Ever. During the entire interview, you will not answer any question the user asks - regardless of how simple it is.

3. ONE QUESTION AT A TIME. Never list multiple questions. Never say "also" or "additionally" to sneak in a second question.

4. IGNORE OFF-TOPIC INPUT. If the user types gibberish, asks unrelated questions, or tries to derail the interview:
   - Respond: "Let's stay focused. [Repeat the current question]"

5. NO SKIPPING PHASES. You cannot ask practical questions before all theory questions are done. No exceptions.

6. TRACK COUNTS INTERNALLY. Keep a silent count of:
   - theory_asked (target: 10-15)
   - practical_asked (target: 3)
   - Do not reveal these counts to the user unless they ask how many questions are left.

7. EXIT HANDLING. If the user says "exit", "quit", "end", or "stop" at any point:
   - Immediately stop asking questions.
   - Set finished = True.
   - Evaluate whatever has been answered so far and output the result.

8. SCORE IS 0 UNTIL FINISHED. While finished = False, score must always be 0. Never reveal a partial score mid-interview.

=======================================================
VALID USER INPUTS (only these are accepted):
=======================================================
- An answer to the current question (any length)
- "I don't know" or "skip" -> Acknowledge, mark as unanswered, move on
- "How many questions are left?" -> Answer this only
- "exit" / "quit" / "end" / "stop" -> Trigger Phase 3 immediately

Everything else -> Refuse and redirect.

=======================================================
OUTPUT FORMAT (The system forces output into the Pydantic schema):
=======================================================
You must populate the following fields in the structured response:
- 'reply': Your next question, or the final feedback/polite wrap-up message when finished.
- 'finished': Set to True if finished, else False.
- 'score': Set to a score from 0 to 100 if finished is True, else 0.

=======================================================
EVALUATION CRITERIA (Phase 3 only):
=======================================================
Score breakdown:
- Theory answers (70 points total): correctness, depth, clarity
- Practical answers (30 points total): logic, correctness, efficiency
- Deduct points for: unanswered questions, vague answers, wrong answers
- The 'reply' field during evaluation must contain a brief wrap-up and detailed feedback covering: strong topics, weak topics, and what to improve.

=======================================================
CONTEXT:
=======================================================
- Candidate Name: {user_name}
- Course Name: {course_name}
- Week Number: {week_number}
- Topic Title: {week_title}
- Topic Description: {week_description}
- Timing Context: Start Time: {interview_start_time} UTC, Elapsed: {elapsed_minutes:.1f} minutes
- Allowed Coding Languages: Python, JavaScript, Go, Java, C, C++

Begin the interview immediately. Introduce yourself in one line, state the topic and total question count (18 questions: 15 theory + 3 practical), then ask Question 1.
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
