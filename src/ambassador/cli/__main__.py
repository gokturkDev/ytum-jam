import argparse
import asyncio
import json
import os
import sys
from uuid import uuid4

import httpx
from dotenv import load_dotenv


async def ask(prompt: str) -> str:
    return await asyncio.to_thread(input, prompt)


async def answer_input() -> str | None:
    print("\nİtirazlara cevabınızı yazın. Göndermek için /gonder, çıkmak için /cik yazın.")
    lines = []
    while True:
        line = await ask("")
        if line == "/cik":
            return None
        if line == "/gonder":
            text = "\n".join(lines)
            if 1 <= len(text.strip()) <= 6000:
                return text
            print("Cevap 1-6000 karakter olmalı. Metninizi yeniden yazın.")
            lines = []
        else:
            lines.append(line)


async def command(client: httpx.AsyncClient, path: str, body: dict, debug: bool = False):
    # body (including request_id) survives all network, provider and busy retries.
    while True:
        print("Halk düşünüyor...")
        try:
            response = await client.post(path, json=body)
            data = response.json()
            if debug:
                print(json.dumps(data, ensure_ascii=False), file=sys.stderr)
            if response.is_success:
                return data
            error = data["error"]
            print(error["message_tr"])
            if not error["retryable"]:
                return None
        except (httpx.TransportError, ValueError, KeyError):
            print("Sunucuya ulaşılamadı. İşlem tamamlanmış olabilir; aynı istekle tekrar deneyin.")
        choice = await ask("Aynı isteği tekrar göndermek için Enter, çıkmak için /cik: ")
        if choice.strip() == "/cik":
            return None


def show_faceoff(game: dict) -> None:
    print(
        f"\nTur {game['round_number']}/{game['total_rounds']} | "
        f"Halk desteği: %{game['support_percent']} | Hedef: %{game['target_percent']}"
    )
    for objection in game["current_objections"]:
        print(f"  {objection['name_tr']}: {objection['text_tr']}")


def show_turn(data: dict) -> None:
    result = data["round"]
    print(f"\n{result['feedback_tr']}")
    print(
        f"Halk desteği: %{result['support_before']} -> %{result['support_after']} "
        f"({result['support_delta']:+d} yüzde puan)"
    )


async def play(
    base_url: str, request_timeout: float, debug: bool, scenario_id: str | None = None
) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=request_timeout) as client:
        try:
            health = await client.get("/health")
            health.raise_for_status()
            if health.json()["backend"] == "fake":
                print(
                    "BETİKLİ DEMO: Cevaplar değerlendirilmez. "
                    "Bu bir yapay zekâ kalite testi değildir."
                )
            if scenario_id is None:
                response = await client.get("/v2/scenarios")
                response.raise_for_status()
                topics = response.json()
                if len(topics) == 1:
                    scenario_id = topics[0]["id"]
                else:
                    print("\nReformcu kralın gündemi:")
                    for index, topic in enumerate(topics, 1):
                        print(
                            f"  {index}. {topic['title_tr']} "
                            f"(%{topic['starting_support']} -> %{topic['target_support']}, "
                            f"{topic['rounds']} tur)"
                        )
                    while True:
                        choice = (await ask("Bir reform seçin (çıkmak için /cik): ")).strip()
                        if choice == "/cik":
                            return
                        if choice.isdecimal() and 1 <= int(choice) <= len(topics):
                            scenario_id = topics[int(choice) - 1]["id"]
                            break
                        print("Listedeki konu numaralarından birini seçin.")
            print("Yüzleşme hazırlanıyor...")
            response = await client.post("/v2/games", json={"scenario_id": scenario_id})
            if not response.is_success:
                print(response.json()["error"]["message_tr"])
                return
            game = response.json()
        except (httpx.HTTPError, ValueError, KeyError):
            print("Sunucuya bağlanılamadı. Önce oyun sunucusunu başlatın.")
            return
        print(f"\n{game['scenario']['title_tr']}\n\n{game['scenario']['decree_tr']}")
        print("Kral yeni bir düzen kurmak istiyor; göreviniz halkın kaygılarına çözüm bulmak.")
        for fact in game["scenario"]["public_facts_tr"]:
            print(f"  - {fact}")
        print(
            f"{game['total_rounds']} turda hedefiniz en az %{game['target_percent']} halk desteği."
        )
        points = game["scoring"]
        print(
            f"İyi cevap: {points['answered']:+d}, kısmi: {points['partial']:+d}, "
            f"yuvarlak: {points['vague']:+d}, çok kötü: {points['missed']:+d} yüzde puan."
        )
        while game["phase"] != "finished":
            show_faceoff(game)
            text = await answer_input()
            if text is None:
                return
            body = {"request_id": str(uuid4()), "expected_version": game["version"], "text": text}
            data = await command(client, f"/v2/games/{game['game_id']}/answers", body, debug)
            if data is None:
                print("Oturum kapatıldı; sunucudaki son oyun durumu korunur.")
                return
            show_turn(data)
            game = data["game"]
        outcome = game["outcome"]
        print(
            f"\n{outcome['message_tr']} Halk desteği: %{outcome['support_percent']} "
            f"(hedef: %{outcome['required_percent']})"
        )
        for effect in outcome["visual_effects"]:
            print(f"Krallıktaki değişim: {effect['description_tr']}")
            for person in effect["name_updates"]:
                print(f"  {person['name_tr']}")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Kralın Elçisi terminal istemcisi")
    parser.add_argument("--base-url", default=os.getenv("CLIENT_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument(
        "--timeout", type=float, default=float(os.getenv("CLIENT_TIMEOUT_SECONDS", "90"))
    )
    parser.add_argument("--scenario", help="Reform kimliği; verilmezse konu seçimi gösterilir")
    parser.add_argument("--debug", action="store_true", help="Yanıtları hata çıkışına yaz")
    args = parser.parse_args()
    try:
        asyncio.run(play(args.base_url, args.timeout, args.debug, args.scenario))
    except (EOFError, KeyboardInterrupt):
        print("\nGörüşmek üzere, elçi.")


if __name__ == "__main__":
    main()
