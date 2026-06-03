import json
import os
import sqlite3
import urllib.request
import urllib.error

from api.services.database import DATABASE_PATH
from api.services.project_service import get_project_names


OPENAI_URL = os.getenv(
    "OPENAI_URL",
    "https://api.openai.com/v1/chat/completions",
)
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_TIMEOUT = int(os.getenv("OPENAI_TIMEOUT", "120"))
MAX_PERSONALITY_QUESTIONS = 5
PROJECT_QUESTION = "Which project are you applying for?"


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
    project_name = user_messages[3] if len(user_messages) >= 4 else None

    return first_name, surname, role, project_name


def count_personality_answers(messages):
    user_answers_count = len(get_user_messages(messages))

    # first_name, surname, role, and project_name are the first 4 user answers
    return max(0, user_answers_count - 4)


def save_chatbot_result(first_name, surname, role, project_name, scores, history):
    conversation_history = json.dumps(history)

    connection = sqlite3.connect(DATABASE_PATH)
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO candidate_personality_scores (
            first_name,
            surname,
            role,
            project_name,
            openness,
            conscientiousness,
            extraversion,
            agreeableness,
            neuroticism,
            conversation_history
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            first_name,
            surname,
            role,
            project_name,
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


def append_candidate_answer(messages, candidate_answer):
    if candidate_answer:
        messages.append(
            {
                "role": "Candidate",
                "content": candidate_answer,
            }
        )


def get_project_options_for_question(question):
    if question == PROJECT_QUESTION:
        return get_project_names()

    return []


def build_chatbot_response(messages, question, is_finished=False, result_id=None):
    first_name, surname, role, project_name = get_candidate_data(messages)

    response = {
        "is_finished": is_finished,
        "question": question,
        "scores": None,
        "first_name": first_name,
        "surname": surname,
        "role": role,
        "project_name": project_name,
        "project_options": get_project_options_for_question(question),
        "history": messages,
    }

    if result_id is not None:
        response["result_id"] = result_id

    return response


def get_initial_question(user_messages_count):
    questions = {
        0: "What is your first name?",
        1: "What is your surname?",
        2: "Which role are you applying for?",
        3: PROJECT_QUESTION,
    }

    return questions.get(user_messages_count)


def should_repeat_last_recruiter_question(messages, candidate_answer):
    return messages and messages[-1]["role"] == "Recruiter" and candidate_answer is None


def build_scoring_messages(messages):
    return [
        {"role": "system", "content": SYSTEM_PROMPT_SCORING},
        *messages,
    ]


def build_final_message(first_name):
    return (
        f"Thank you for the conversation, {first_name}. "
        "I wish you the best of luck in the recruitment process."
    )


def finish_interview(messages):
    first_name, surname, role, project_name = get_candidate_data(messages)
    raw_scores = call_openai(build_scoring_messages(messages), json_format=True)
    scores = json.loads(raw_scores)
    final_message = build_final_message(first_name)

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
        project_name=project_name,
        scores=scores,
        history=messages,
    )

    return build_chatbot_response(
        messages,
        question=final_message,
        is_finished=True,
        result_id=result_id,
    )


def build_personality_prompt(role, project_name, question_number):
    return (
        f"The candidate is applying for the role: {role}. "
        f"The candidate is applying for the project: {project_name}. "
        "Use this only as hidden context. "
        "Do not mention the role directly in the question. "
        f"Ask personality question number {question_number} "
        f"out of {MAX_PERSONALITY_QUESTIONS}. "
        "Return only one neutral question. "
        "Do not include examples, hints, explanations, praise, or commentary."
    )


def build_recruiter_messages(messages, role, project_name, question_number):
    return [
        {"role": "system", "content": SYSTEM_PROMPT_RECRUITER},
        *messages,
        {
            "role": "Candidate",
            "content": build_personality_prompt(
                role,
                project_name,
                question_number,
            ),
        },
    ]


def generate_personality_question(messages):
    _, _, role, project_name = get_candidate_data(messages)
    personality_answers_count = count_personality_answers(messages)
    question_number = personality_answers_count + 1
    recruiter_messages = build_recruiter_messages(
        messages,
        role,
        project_name,
        question_number,
    )

    return call_openai(recruiter_messages)


def candidate_chatbot(history, candidate_answer=None):
    messages = list(history)
    append_candidate_answer(messages, candidate_answer)

    if should_repeat_last_recruiter_question(messages, candidate_answer):
        return build_chatbot_response(messages, messages[-1]["content"])

    user_messages_count = len(get_user_messages(messages))
    question = get_initial_question(user_messages_count)

    if question is None:
        if count_personality_answers(messages) >= MAX_PERSONALITY_QUESTIONS:
            return finish_interview(messages)

        question = generate_personality_question(messages)

    messages.append(
        {
            "role": "Recruiter",
            "content": question,
        }
    )

    return build_chatbot_response(messages, question)
