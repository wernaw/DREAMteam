import json
import urllib.request
import urllib.error


OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "llama3"
MAX_PERSONALITY_QUESTIONS = 5


SYSTEM_PROMPT_RECRUITER = """
You are a recruiter conducting an interview with a candidate.

The first assistant question must ask which role the candidate is applying for.
After the candidate answers with the role, use that role as context for all next questions.

Your goal is to assess the candidate's personality using the Big Five model:
- Openness: imagination, curiosity, new experiences, ideas, culture, aesthetics.
- Conscientiousness: organization, consistency, planning, reliability, long-term goals.
- Extraversion: sociability, energy, talkativeness, social activity.
- Agreeableness: cooperation, trust, maintaining relationships, adapting to others.
- Neuroticism: stress sensitivity, nervousness, emotional fluctuations.

Rules:
- after the role question, ask a maximum of 5 personality questions,
- ask only one question at a time,
- adapt each next question to the candidate's previous answer,
- use the candidate's role only as hidden context when choosing what to explore,
- do not mention the role directly in the personality questions,
- ask general, neutral, behavioral questions about real situations, decisions, preferences, and reactions,
- do not ask questions that sound specific to the candidate's job title,
- do not mention Big Five trait names in the questions,
- do not ask leading questions,
- do not suggest what answer would be positive or expected,
- do not include examples of possible answers,
- do not praise or judge the candidate's previous answer,
- questions should sound natural and professional, but not role-specific,
- respond in English.
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


def call_ollama(messages, json_format=False):
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
    }

    if json_format:
        payload["format"] = "json"

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8")
        raise RuntimeError(
            f"Ollama returned HTTP {error.code}: {error_body}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError("Ollama is not running.") from error

    return data["message"]["content"].strip()


def get_candidate_role(messages):
    user_messages = [
        message["content"] for message in messages if message["role"] == "user"
    ]

    if not user_messages:
        return None

    return user_messages[0]


def count_personality_answers(messages):
    user_answers_count = sum(1 for message in messages if message["role"] == "user")

    return max(0, user_answers_count - 1)


def candidate_chatbot(history, candidate_answer=None):
    messages = list(history)

    if candidate_answer:
        messages.append(
            {
                "role": "user",
                "content": candidate_answer,
            }
        )

    if messages and messages[-1]["role"] == "assistant" and candidate_answer is None:
        return {
            "is_finished": False,
            "question": messages[-1]["content"],
            "scores": None,
            "role": get_candidate_role(messages),
            "history": messages,
        }

    if not messages:
        question = "Which role are you applying for?"

        messages.append(
            {
                "role": "assistant",
                "content": question,
            }
        )

        return {
            "is_finished": False,
            "question": question,
            "scores": None,
            "role": None,
            "history": messages,
        }

    role = get_candidate_role(messages)
    personality_answers_count = count_personality_answers(messages)

    if role and personality_answers_count >= MAX_PERSONALITY_QUESTIONS:
        scoring_messages = [
            {"role": "system", "content": SYSTEM_PROMPT_SCORING},
            *messages,
        ]

        raw_scores = call_ollama(scoring_messages, json_format=True)
        scores = json.loads(raw_scores)

        return {
            "is_finished": True,
            "question": None,
            "scores": scores,
            "role": role,
            "history": messages,
        }

    if role is None:
        question = "Which role are you applying for?"
    else:
        recruiter_messages = [
            {"role": "system", "content": SYSTEM_PROMPT_RECRUITER},
            *messages,
            {
                "role": "user",
                "content": (
                    f"The candidate is applying for the role: {role}. "
                    f"Ask personality question number {personality_answers_count + 1} "
                    f"out of {MAX_PERSONALITY_QUESTIONS}. "
                    "Return only one neutral question. "
                    "Do not include examples, hints, explanations, praise, or commentary."
                ),
            },
        ]

        question = call_ollama(recruiter_messages)

    messages.append(
        {
            "role": "assistant",
            "content": question,
        }
    )

    return {
        "is_finished": False,
        "question": question,
        "scores": None,
        "role": role,
        "history": messages,
    }
