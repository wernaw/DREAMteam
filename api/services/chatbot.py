import json
import os
import sqlite3
import urllib.request
import urllib.error
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

OPENAI_URL = os.getenv(
    "OPENAI_URL",
    "https://api.openai.com/v1/chat/completions",
)
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_TIMEOUT = int(os.getenv("OPENAI_TIMEOUT", "120"))
MAX_PERSONALITY_QUESTIONS = 5

DATABASE_PATH = PROJECT_ROOT / os.getenv("DATABASE_PATH", "api/dreamteam")


SYSTEM_PROMPT_RECRUITER = """
You are a recruiter conducting an interview with a candidate.

Use the candidate's role only as hidden context when choosing what to explore.
Do not mention the role directly in the personality questions.

Your goal is to assess the candidate's personality using the Big Five model:
- Openness: imagination, curiosity, new experiences, ideas, culture, aesthetics.
- Conscientiousness: organization, consistency, planning, reliability, long-term goals.
- Extraversion: sociability, energy, talkativeness, social activity.
- Agreeableness: cooperation, trust, maintaining relationships, adapting to others.
- Neuroticism: stress sensitivity, nervousness, emotional fluctuations.

Rules:
- ask a maximum of 5 personality questions,
- adapt each next question to the candidate's previous answer,
- ask general, neutral, behavioral questions,
- do not ask questions that sound specific to the candidate's job title,
- do not mention Big Five trait names,
- do not ask leading questions,
- do not suggest what answer would be positive or expected,
- do not include examples of possible answers,
- do not praise or judge the candidate's previous answer,
- respond in English.
- do not repeat greetings, introductions, or statements like "I'm excited to learn more about you" after the interview has started.
- ask exactly one question at a time.
- after the candidate answers, briefly acknowledge the answer in one natural sentence, then ask the next question.
- maintain continuity with the previous exchange.
- do not restart the interview or reintroduce the interview format.
- do not say "Let's start" or "Here's my first question" unless it is truly the first interview question.
- if the role has already been provided, do not ask for it again.

End-of-interview rule:
- When the interview is complete, do not ask another question.
- Thank the candidate for the conversation in a warm, professional way.
- Briefly wish them success in the recruitment process.
"""


SYSTEM_PROMPT_SCORING = """
Based on the conversation, assess the candidate's personality using the Big Five model.

Use the role the candidate is applying for as context, but score only the personality traits.

Return only valid JSON without any additional comment.
Each value must be a number from 0 to 1.

Format:
{
  "openness": 0.0,
  "conscientiousness": 0.0,
  "extraversion": 0.0,
  "agreeableness": 0.0,
  "neuroticism": 0.0
}
"""


def to_openai_messages(messages):
    role_mapping = {
        "Candidate": "user",
        "Recruiter": "assistant",
        "system": "system",
        "user": "user",
        "assistant": "assistant",
    }

    return [
        {
            "role": role_mapping.get(message["role"], "user"),
            "content": message["content"],
        }
        for message in messages
    ]


def call_openai(messages, json_format=False):
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set.")

    payload = {
        "model": OPENAI_MODEL,
        "messages": to_openai_messages(messages),
        "temperature": 0.2,
    }

    if json_format:
        payload["response_format"] = {"type": "json_object"}

    request = urllib.request.Request(
        OPENAI_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=OPENAI_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8")
        raise RuntimeError(
            f"OpenAI API returned HTTP {error.code}: {error_body}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError("Could not connect to OpenAI API.") from error

    return data["choices"][0]["message"]["content"].strip()


def get_user_messages(messages):
    return [
        message["content"] for message in messages if message["role"] == "Candidate"
    ]


def get_candidate_data(messages):
    user_messages = get_user_messages(messages)

    first_name = user_messages[0] if len(user_messages) >= 1 else None
    surname = user_messages[1] if len(user_messages) >= 2 else None
    role = user_messages[2] if len(user_messages) >= 3 else None

    return first_name, surname, role


def count_personality_answers(messages):
    user_answers_count = len(get_user_messages(messages))

    # first_name, surname, and role are the first 3 user answers
    return max(0, user_answers_count - 3)


def save_chatbot_result(first_name, surname, role, scores, history):
    conversation_history = json.dumps(history)

    connection = sqlite3.connect(DATABASE_PATH)
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO candidate_personality_scores (
            first_name,
            surname,
            role,
            openness,
            conscientiousness,
            extraversion,
            agreeableness,
            neuroticism,
            conversation_history
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            first_name,
            surname,
            role,
            scores["openness"],
            scores["conscientiousness"],
            scores["extraversion"],
            scores["agreeableness"],
            scores["neuroticism"],
            conversation_history,
        ),
    )

    connection.commit()
    result_id = cursor.lastrowid
    connection.close()

    return result_id


def candidate_chatbot(history, candidate_answer=None):
    messages = list(history)

    if candidate_answer:
        messages.append(
            {
                "role": "Candidate",
                "content": candidate_answer,
            }
        )

    if messages and messages[-1]["role"] == "Recruiter" and candidate_answer is None:
        first_name, surname, role = get_candidate_data(messages)

        return {
            "is_finished": False,
            "question": messages[-1]["content"],
            "scores": None,
            "first_name": first_name,
            "surname": surname,
            "role": role,
            "history": messages,
        }

    user_messages = get_user_messages(messages)

    if len(user_messages) == 0:
        question = "What is your first name?"
    elif len(user_messages) == 1:
        question = "What is your surname?"
    elif len(user_messages) == 2:
        question = "Which role are you applying for?"
    else:
        first_name, surname, role = get_candidate_data(messages)
        personality_answers_count = count_personality_answers(messages)

        if personality_answers_count >= MAX_PERSONALITY_QUESTIONS:
            scoring_messages = [
                {"role": "system", "content": SYSTEM_PROMPT_SCORING},
                *messages,
            ]

            raw_scores = call_openai(scoring_messages, json_format=True)
            scores = json.loads(raw_scores)

            final_message = (
                f"Thank you for the conversation, {first_name}. "
                "I wish you the best of luck in the recruitment process."
            )
            messages.append(
                {
                    "role": "Recruiter",
                    "content": final_message,
                }
            )

            result_id = save_chatbot_result(
                first_name=first_name,
                surname=surname,
                role=role,
                scores=scores,
                history=messages,
            )

            return {
                "is_finished": True,
                "question": final_message,
                "scores": None,
                "first_name": first_name,
                "surname": surname,
                "role": role,
                "result_id": result_id,
                "history": messages,
            }

        recruiter_messages = [
            {"role": "system", "content": SYSTEM_PROMPT_RECRUITER},
            *messages,
            {
                "role": "Candidate",
                "content": (
                    f"The candidate is applying for the role: {role}. "
                    "Use this only as hidden context. "
                    "Do not mention the role directly in the question. "
                    f"Ask personality question number {personality_answers_count + 1} "
                    f"out of {MAX_PERSONALITY_QUESTIONS}. "
                    "Return only one neutral question. "
                    "Do not include examples, hints, explanations, praise, or commentary."
                ),
            },
        ]

        question = call_openai(recruiter_messages)

    messages.append(
        {
            "role": "Recruiter",
            "content": question,
        }
    )

    first_name, surname, role = get_candidate_data(messages)

    return {
        "is_finished": False,
        "question": question,
        "scores": None,
        "first_name": first_name,
        "surname": surname,
        "role": role,
        "history": messages,
    }
