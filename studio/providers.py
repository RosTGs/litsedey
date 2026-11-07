"""Provider adapters. No credentials enter project files or browser responses."""
from __future__ import annotations
import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from um import comfy

class ProviderError(RuntimeError):
    pass

def fail(message, code=1):
    raise ProviderError(message)

comfy.die = fail

def request(url, body=None, key=None, raw=False, timeout=30):
    headers = {'Content-Type': 'application/json'}
    if key:
        headers['Authorization'] = 'Key ' + key
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            result = response.read(80 * 1024 * 1024 + 1)
            if len(result) > 80 * 1024 * 1024:
                raise ProviderError('Результат превышает 80 МБ')
            return result if raw else json.loads(result)
    except urllib.error.HTTPError as e:
        # Do not echo remote error bodies: they may contain submitted private data.
        raise ProviderError('Сервис вернул HTTP %d. Проверьте модель, входные данные и баланс.' % e.code) from None
    except urllib.error.URLError:
        raise ProviderError('Не удалось подключиться к сервису. Проверьте адрес и доступность.') from None

def queue_url(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname != 'queue.fal.run' or parsed.username or parsed.port not in (None, 443):
        raise ProviderError('Некорректный адрес очереди fal')
    return url

def download_url(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != 'https' or not any((parsed.hostname or '').endswith('.' + d) or parsed.hostname == d
                                         for d in ('fal.media', 'fal.run', 'fal.ai')) or parsed.username or parsed.port not in (None, 443):
        raise ProviderError('Результат вне поддерживаемого хранилища fal')
    return url

def generate(config, spec, reference, update):
    """Yield images as bytes. Callback persists remote id before polling."""
    provider = spec['provider']
    if provider == 'fal':
        key = config.get('fal_key', '')
        if not key:
            raise ProviderError('Добавьте ключ fal в настройках подключений')
        endpoint = spec.get('endpoint', 'fal-ai/flux/schnell')
        if not isinstance(endpoint, str) or not endpoint or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-/.' for c in endpoint) or '..' in endpoint:
            raise ProviderError('Некорректный ID модели fal')
        inputs = dict(spec.get('inputs') or {})
        if spec.get('prompt'):
            inputs['prompt'] = spec['prompt']
        if reference:
            uri = 'data:image/png;base64,' + base64.b64encode(reference).decode()
            field = spec.get('reference_field', 'image_urls')
            if field not in ('image_url', 'image_urls'):
                raise ProviderError('Поле референса: image_url или image_urls')
            inputs[field] = [uri] if field.endswith('urls') else uri
        job = request('https://queue.fal.run/' + endpoint, inputs, key)
        status_url, result_url = queue_url(job['status_url']), queue_url(job['response_url'])
        update(remote_id=job['request_id'], remote_status='IN_QUEUE', status_url=status_url, response_url=result_url)
        end = time.monotonic() + 1200
        while time.monotonic() < end:
            state = request(status_url, key=key)
            update(remote_status=state.get('status', 'UNKNOWN'))
            if state.get('status') in ('FAILED', 'CANCELLED') or state.get('error'):
                raise ProviderError('Генерация завершилась ошибкой на стороне fal')
            if state.get('status') == 'COMPLETED':
                result = request(result_url, key=key)
                images = result.get('images') or ([result['image']] if result.get('image') else [])
                if not images:
                    raise ProviderError('Модель не вернула изображения. Используйте endpoint для изображений.')
                for item in images[:8]:
                    yield request(download_url(item['url']), raw=True, timeout=120)
                return
            time.sleep(2)
        raise ProviderError('Ожидание превысило 20 минут. ID запроса сохранён в истории; повторный запрос может списать средства.')
    elif provider == 'comfy':
        base = config.get('comfy_url', 'http://127.0.0.1:8188').rstrip('/')
        workflow = spec.get('workflow')
        if not workflow:
            if reference:
                raise ProviderError('Для референса в ComfyUI загрузите собственный API workflow; встроенный шаблон работает с текстом')
            checkpoint = spec.get('checkpoint')
            if not checkpoint:
                raise ProviderError('Укажите имя установленного checkpoint ComfyUI')
            workflow = comfy.txt2img(spec['prompt'], checkpoint, width=768, height=1024, seed=int(spec.get('seed', 0)))
        if not isinstance(workflow, dict) or not workflow or not all(isinstance(v, dict) and 'class_type' in v for v in workflow.values()):
            raise ProviderError('Нужен workflow в формате Export (API) из ComfyUI')
        # The custom graph owns prompts, reference inputs and seeds. No implicit rewriting.
        job = request(base + '/prompt', {'prompt': workflow})
        if not job.get('prompt_id') or job.get('node_errors'):
            raise ProviderError('ComfyUI отклонил workflow. Проверьте узлы и модели.')
        pid = job['prompt_id']
        update(remote_id=pid, remote_status='IN_QUEUE')
        end = time.monotonic() + 1200
        while time.monotonic() < end:
            result = request(base + '/history/' + urllib.parse.quote(pid, safe='')).get(pid)
            if result:
                state = result.get('status', {})
                if state.get('status_str') == 'error':
                    raise ProviderError('Ошибка выполнения ComfyUI. Подробности в его журнале.')
                if state.get('completed', True):
                    outputs = comfy.outputs(result)
                    if not outputs:
                        raise ProviderError('В workflow отсутствует сохранённое изображение. Добавьте SaveImage.')
                    for item in outputs[:8]:
                        query = urllib.parse.urlencode({k: item.get(k, '') for k in ('filename', 'subfolder', 'type')})
                        yield request(base + '/view?' + query, raw=True, timeout=120)
                    return
            time.sleep(2)
        raise ProviderError('Ожидание ComfyUI превысило 20 минут. ID запроса сохранён.')
    else:
        raise ProviderError('Неизвестный провайдер')
