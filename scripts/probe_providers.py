"""Liste les modèles GRATUITS de l'API classique Pollinations + teste un vrai appel chat.

    python -m scripts.probe_providers
"""

import asyncio
import json

import httpx

TEXT_FREE = "https://text.pollinations.ai"


async def main() -> None:
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.get(f"{TEXT_FREE}/models")
        print(f"GET /models -> {r.status_code}")
        models = []
        try:
            data = r.json()
            models = [m.get("name") if isinstance(m, dict) else m for m in data]
        except Exception:  # noqa: BLE001
            print(r.text[:500])
        print("Modèles gratuits (classic) :", models)

        # Essais d'appel réels avec plusieurs noms de modèles
        for model in models[:4] + [None]:
            payload = {"messages": [{"role": "user", "content": "Réponds uniquement : KYRO"}]}
            if model:
                payload["model"] = model
            try:
                rr = await c.post(f"{TEXT_FREE}/openai", json=payload)
                body = rr.text[:220].replace("\n", " ")
                print(f"\nPOST /openai model={model!r} -> {rr.status_code}")
                print(f"   {body}")
                if rr.status_code == 200:
                    try:
                        j = rr.json()
                        print("   RÉPONSE :", j["choices"][0]["message"]["content"][:120])
                    except Exception:  # noqa: BLE001
                        pass
            except Exception as e:  # noqa: BLE001
                print(f"\nPOST /openai model={model!r} -> ERREUR {type(e).__name__}: {e}")

        # Sans modèle, sur /v1/chat/completions (compatible OpenAI standard)
        print("\n--- /v1/chat/completions ---")
        try:
            rr = await c.post(f"{TEXT_FREE}/v1/chat/completions",
                              json={"messages": [{"role": "user", "content": "Réponds : OK"}]})
            print(f"-> {rr.status_code} | {rr.text[:220]}")
        except Exception as e:  # noqa: BLE001
            print(f"-> ERREUR {type(e).__name__}: {e}")


asyncio.run(main())
