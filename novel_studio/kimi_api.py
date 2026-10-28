import json
import socket
import urllib.error
import urllib.request


class APIError(Exception):
    pass


def friendly_http_error(status, body):
    text = body.lower()
    if status == 401:
        return (
            "认证失败：Key 无效、已过期，或与当前接口类型不匹配。"
            "开放平台 Key 请选择“Kimi 开放平台”，地址 https://api.moonshot.cn/v1，模型 kimi-k3.1-pro；"
            "会员 Key 请选择“Kimi Code”，地址 https://api.kimi.com/coding/v1，模型 k3.1-pro。"
        )
    if status == 403:
        return "这个账号暂时不能使用所选模型。请检查会员权限，或在 API 设置中换成账号可用的模型。"
    if status == 404:
        return "API 地址不对。国内 Kimi Code 地址通常是 https://api.kimi.com/coding/v1。"
    if status == 429:
        if "quota" in text or "balance" in text or "insufficient" in text:
            return "账号可用额度不足，或已经达到使用上限。请查看 Kimi 控制台。"
        return "请求太频繁了。请稍等一会儿，再点一次。"
    if status == 400:
        return "API 没有接受这次请求。请检查模型名称是否为 k3.1-pro，以及 API 地址是否正确。"
    if status >= 500:
        return "Kimi 服务暂时忙或出现异常。你的原稿没有受影响，请稍后再试。"
    return f"连接 API 失败（服务返回 {status}）。请检查设置后再试。"


class KimiAPI:
    def __init__(self, credentials):
        self.api_key = credentials["api_key"]
        self.base_url = credentials["base_url"].rstrip("/")
        self.model = credentials["model"]
        if self.base_url.endswith("/chat/completions"):
            self.endpoint = self.base_url
        else:
            self.endpoint = self.base_url + "/chat/completions"

    def request(self, messages, stream=True, max_tokens=8192):
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "max_tokens": max_tokens,
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + self.api_key,
                "Content-Type": "application/json",
                "Accept": "text/event-stream" if stream else "application/json",
                "User-Agent": "NovelStudio/1.0",
            },
            method="POST",
        )
        try:
            return urllib.request.urlopen(request, timeout=240)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise APIError(friendly_http_error(exc.code, body)) from None
        except (TimeoutError, socket.timeout):
            raise APIError("等了很久还没有收到回复。请检查网络后再试，原稿已经保留。") from None
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                message = "连接超时了。请检查网络后再试，原稿已经保留。"
            else:
                message = "连不上 Kimi 服务器。请检查网络、API 地址，以及电脑是否能正常上网。"
            raise APIError(message) from None

    def test(self):
        with self.request(
            [{"role": "user", "content": "请只回复：连接成功"}],
            stream=False,
            max_tokens=512,
        ) as response:
            try:
                payload = json.loads(response.read().decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise APIError("服务器回复了无法识别的内容。请检查 API 地址是否填对。") from None
        if payload.get("error"):
            raise APIError("API 返回错误，请检查 Key、模型权限和额度。")
        return "连接成功，所选模型已经回应。"

    def complete(self, messages, max_tokens=4096):
        with self.request(messages, stream=False, max_tokens=max_tokens) as response:
            try:
                payload = json.loads(response.read().decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise APIError("服务器回复了无法识别的内容，请重试。") from None
        if payload.get("error"):
            raise APIError("API 返回错误，请检查 Key、模型权限和额度。")
        choices = payload.get("choices") or []
        content = (choices[0].get("message") or {}).get("content") if choices else ""
        if not str(content or "").strip():
            raise APIError("模型没有返回小传内容，请重试。")
        return str(content).strip()

    def stream(self, messages):
        try:
            response = self.request(messages, stream=True)
        except APIError:
            raise
        emitted = False
        reasoning = False
        with response:
            while True:
                try:
                    raw = response.readline()
                except (TimeoutError, socket.timeout):
                    raise APIError("生成中途连接超时。已经收到的文字会保留，请稍后重试。") from None
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if not line or line.startswith(":") or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if payload.get("error"):
                    raise APIError("生成被 API 中断。请检查额度与模型权限后重试。")
                choices = payload.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                if delta.get("reasoning_content") and not reasoning:
                    reasoning = True
                    yield {"type": "status", "message": "Kimi 正在构思，马上开始写……"}
                content = delta.get("content")
                if content:
                    emitted = True
                    yield {"type": "delta", "content": content}
        if not emitted:
            raise APIError("模型这次没有给出正文。请再试一次，或把要求写得更具体一些。")
        yield {"type": "done"}
