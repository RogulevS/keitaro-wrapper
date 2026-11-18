from __future__ import annotations

import httpx


class KeitaroError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status
        self.message = message


def as_list(payload) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("rows", "data", "items"):
            if isinstance(payload.get(key), list):
                return payload[key]
    raise KeitaroError("Keitaro вернул не список")


class KeitaroClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 30):
        if not base_url or not api_key:
            raise KeitaroError("Не заданы адрес трекера и API-ключ")
        self.base_url = base_url.rstrip("/") + "/admin_api/v1"
        self.api_key = api_key
        self.timeout = timeout

    def request(self, method: str, path: str, json_body: dict | None = None, params: dict | None = None):
        url = self.base_url + path
        try:
            response = httpx.request(
                method,
                url,
                json=json_body,
                params=params,
                headers={"Api-Key": self.api_key, "Accept": "application/json"},
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise KeitaroError(f"Запрос к Keitaro не выполнен: {exc}") from exc
        if response.status_code >= 400:
            raise KeitaroError(self._error_message(response), response.status_code)
        if not response.content:
            return None
        return response.json()

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            text = response.text.strip()
            return text or f"Keitaro ответил {response.status_code}"
        if isinstance(payload, dict):
            for key in ("error", "message", "description"):
                if payload.get(key):
                    return str(payload[key])
            return str(payload)
        return str(payload)

    def get(self, path: str, params: dict | None = None):
        return self.request("GET", path, params=params)

    def post(self, path: str, body: dict):
        return self.request("POST", path, json_body=body)

    def put(self, path: str, body: dict):
        return self.request("PUT", path, json_body=body)

    def campaigns(self) -> list[dict]:
        return as_list(self.get("/campaigns"))

    def campaign(self, campaign_id: int) -> dict:
        payload = self.get(f"/campaigns/{campaign_id}")
        if not isinstance(payload, dict):
            raise KeitaroError("Кампания не найдена")
        return payload

    def create_campaign(self, body: dict) -> dict:
        payload = self.post("/campaigns", body)
        if not isinstance(payload, dict) or "id" not in payload:
            raise KeitaroError("Keitaro не вернул id кампании")
        return payload

    def campaign_streams(self, campaign_id: int) -> list[dict]:
        return as_list(self.get(f"/campaigns/{campaign_id}/streams"))

    def create_stream(self, body: dict) -> dict:
        payload = self.post("/streams", body)
        if not isinstance(payload, dict) or "id" not in payload:
            raise KeitaroError("Keitaro не вернул id потока")
        return payload

    def update_stream_offers(self, stream_id: int, offers: list[dict]) -> dict:
        current = self.get(f"/streams/{stream_id}")
        if not isinstance(current, dict):
            raise KeitaroError("Поток не найден")
        current["offers"] = offers
        for key in ("id", "updated_at", "created_at", "offer_selection"):
            current.pop(key, None)
        payload = self.put(f"/streams/{stream_id}", current)
        return payload if isinstance(payload, dict) else current

    def offers(self) -> list[dict]:
        return as_list(self.get("/offers"))

    def domains(self) -> list[dict]:
        return as_list(self.get("/domains"))

    def groups(self) -> list[dict]:
        return as_list(self.get("/groups", params={"type": "campaigns"}))

    def traffic_sources(self) -> list[dict]:
        return as_list(self.get("/traffic_sources"))

    def stream_filters(self) -> list:
        return as_list(self.get("/stream_filters"))

    def stream_actions(self) -> list:
        return as_list(self.get("/streams_actions"))
