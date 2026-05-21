from api.services.chatbot import candidate_chatbot
import json


if __name__ == "__main__":
    history = []

    print("Candidate chatbot started. Type your answers below.\n")

    while True:
        response = candidate_chatbot(history)

        if response["is_finished"]:
            print("\nFinal Big Five scores:")
            print(json.dumps(response["scores"], indent=2))
            break

        question = response["question"]
        history = response["history"]

        print(f"Recruiter: {question}")

        answer = input("Candidate: ")

        response = candidate_chatbot(history, candidate_answer=answer)
        history = response["history"]

        if response["is_finished"]:
            print("\nFinal Big Five scores:")
            print(json.dumps(response["scores"], indent=2))
            break
