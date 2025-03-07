from CLI               import konsol
from fastapi           import Request, Response
from fastapi.responses import StreamingResponse
from .            import home_router
from urllib.parse import unquote
import httpx, asyncio, json, time, traceback

# Sabit değerler
DEFAULT_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_5)"
DEFAULT_REFERER    = "https://twitter.com/"
DEFAULT_CHUNK_SIZE = 1024 * 64   # 64KB
HLS_BUFFER_SIZE    = 1024 * 256  # 256KB
TS_BUFFER_SIZE     = 1024 * 512  # 512KB
MAX_BUFFER_SIZE    = 1024 * 1024 # 1MB

# Content-Type helpers
CONTENT_TYPES = {
    ".m3u8"   : "application/vnd.apple.mpegurl",
    ".ts"     : "video/mp2t",
    ".mp4"    : "video/mp4",
    ".webm"   : "video/webm",
    ".mkv"    : "video/x-matroska",
    "default" : "video/mp4",
}

# Önemli HTTP başlıkları
IMPORTANT_HEADERS = [
    "Content-Length",
    "Content-Range",
    "Content-Type",
    "Accept-Ranges",
    "ETag",
    "Cache-Control",
    "X-Content-Duration",
    "Content-Duration",
    "Content-Disposition",
]

# CORS ayarları
CORS_HEADERS = {
    "Access-Control-Allow-Origin"  : "*",
    "Access-Control-Allow-Methods" : "GET, HEAD, OPTIONS",
    "Access-Control-Allow-Headers" : "Origin, Content-Type, Accept, Range",
}

# HLS özel başlıkları
HLS_HEADERS = {
    "Cache-Control" : "no-cache, no-store, must-revalidate",
    "Pragma"        : "no-cache",
    "Expires"       : "0",
}

async def create_httpx_client():
    """Gelişmiş yapılandırma ile HTTPX istemci oluştur"""
    return httpx.AsyncClient(
        follow_redirects = True,
        # Daha yüksek zaman aşımı değerleri
        timeout          = httpx.Timeout(
            connect = 10.0,  # Bağlantı zaman aşımı
            read    = 120.0,    # Okuma zaman aşımı (2 dakika)
            write   = 10.0,    # Yazma zaman aşımı
            pool    = 10.0      # Havuz zaman aşımı
        ),
        # Geliştirilmiş yeniden deneme stratejisi
        transport        = httpx.AsyncHTTPTransport(
            retries = 3,  # 3 yeniden deneme
        ),
        # Daha büyük bağlantı havuzu
        limits           = httpx.Limits(
            max_keepalive_connections = 20,
            max_connections           = 50,
            keepalive_expiry          = 30.0
        )
    )


async def get_client_headers(request: Request, referer: str, headers: dict):
    """İstemci başlıklarını hazırla"""
    # User-Agent belirleme
    user_agent = headers.get("User-Agent", DEFAULT_USER_AGENT)

    # Temel başlıklar
    client_headers = {
        "User-Agent"      : user_agent,
        "Accept"          : "*/*",
        "Accept-Encoding" : "identity",
        "Connection"      : "keep-alive",
        "Cache-Control"   : "no-cache",
    }

    # Range header varsa ekle
    if "Range" in request.headers:
        client_headers["Range"] = request.headers["Range"]

    # Referer bilgisi ekle
    if referer and referer != "None":
        client_headers["Referer"] = unquote(referer)
    else:
        client_headers["Referer"] = DEFAULT_REFERER

    # Ek özel başlıkları ekle
    for key, value in headers.items():
        if key.lower() not in [h.lower() for h in client_headers.keys()]:
            client_headers[key] = value

    return client_headers


def get_response_headers(response_headers: dict[str, str], url: str):
    """Yanıt başlıklarını hazırla"""
    resp_headers = {}

    # Önemli başlıkları kopyala
    for header in IMPORTANT_HEADERS:
        if header.lower() in response_headers:
            resp_headers[header] = response_headers[header.lower()]

    # Content-Type kontrolü
    if "Content-Type" not in resp_headers:
        # URL'e göre uygun Content-Type belirleme
        for ext, content_type in CONTENT_TYPES.items():
            if ext in url:
                resp_headers["Content-Type"] = content_type
                break
        else:
            resp_headers["Content-Type"] = CONTENT_TYPES["default"]

    # CORS başlıklarını ekle
    resp_headers.update(CORS_HEADERS)

    # HLS için özel handling
    content_type = resp_headers.get("Content-Type", "").lower()
    if "mpegurl" in content_type or content_type == "application/vnd.apple.mpegurl":
        resp_headers.update(HLS_HEADERS)

    # Accept-Ranges header'ı yoksa ekle
    if "Accept-Ranges" not in resp_headers:
        resp_headers["Accept-Ranges"] = "bytes"

    return resp_headers


async def stream_video_content(response, url: str, content_type: str):
    """Video içeriğini akışlı olarak gönder - İyileştirilmiş"""
    try:
        buffer      = b""
        chunk_size  = DEFAULT_CHUNK_SIZE
        buffer_size = DEFAULT_CHUNK_SIZE
        total_bytes = 0
        is_hls      = False
        is_ts       = False
        start_time  = time.time()
        
        # İçerik türüne göre tampon boyutunu ayarla
        if "mpegurl" in content_type.lower() or content_type == "application/vnd.apple.mpegurl":
            buffer_size = HLS_BUFFER_SIZE
            is_hls      = True
        elif "mp2t" in content_type.lower() or url.endswith(".ts"):
            buffer_size = TS_BUFFER_SIZE
            is_ts       = True
        
        # Maksimum tampon boyutunu sınırla
        buffer_size = min(buffer_size, MAX_BUFFER_SIZE)
        
        async for chunk in response.aiter_bytes(chunk_size=chunk_size):
            # Veri toplam boyutu
            total_bytes += len(chunk)
            
            # HLS veya TS segment'leri için buffer kullan
            if is_hls or is_ts:
                buffer += chunk
                # Tampon eşiğini belirle
                if len(buffer) >= buffer_size:
                    yield buffer
                    buffer = b""
            else:
                # Normal video için direkt gönder
                yield chunk
            
            # Çok fazla CPU kullanımını önlemek için her 1MB veri sonrasında kısa bekleme
            if total_bytes % (1024 * 1024) == 0:
                await asyncio.sleep(0.001)  # 1ms bekleme
        
        # Kalan tampon varsa gönder
        if buffer:
            yield buffer
        
        elapsed = time.time() - start_time
        konsol.print(f"Video akışı tamamlandı: {total_bytes/1024/1024:.2f}MB, {elapsed:.2f}s içinde")
    except Exception as stream_error:
        konsol.print(f"Stream hatası: {str(stream_error)}")
        konsol.print(traceback.format_exc())
        # Hatayı ana fonksiyona bildir
        raise


async def handle_errors(status_code, message):
    """Hata yanıtları için yardımcı fonksiyon"""
    headers = {
        "Content-Type": "text/plain",
        **CORS_HEADERS
    }
    
    return {
        "status_code" : status_code,
        "headers"     : headers,
        "content"     : message.encode()
    }


@home_router.get("/proxy/video")
async def video_proxy(request: Request, url: str, referer: str = None, headers: str = None):
    """Video proxy endpoint'i - İyileştirilmiş"""
    start_time = time.time()
    
    try:
        # URL'i decode et
        decoded_url = unquote(url)
        
        # İstemci başlıklarını decode et
        decoded_headers = {}
        if headers:
            try:
                decoded_headers = json.loads(headers)
            except json.JSONDecodeError as e:
                konsol.print(f"Header parsing hatası: {str(e)}")
        
        # İstemci başlıklarını hazırla
        client_headers = await get_client_headers(request, referer, decoded_headers)
        
        konsol.print(f"Proxy isteği: {decoded_url[:100]}...")
        
        # Stream yanıtı için generator
        async def stream_generator():
            # Geliştirilmiş HTTPX istemcisi oluştur
            try:
                async with await create_httpx_client() as client:
                    try:
                        async with client.stream("GET", decoded_url, headers=client_headers) as response:
                            if response.status_code >= 400:
                                error_msg = f"Kaynak sunucu hatası: HTTP {response.status_code}"
                                konsol.print(f"Hata: {error_msg}")
                                yield await handle_errors(response.status_code, error_msg)
                                return
                            
                            # Yanıt başlıklarını hazırla
                            resp_headers = get_response_headers(response.headers, decoded_url)
                            
                            # İlk yanıt başlıklarını gönder
                            yield {
                                "status_code" : response.status_code,
                                "headers"     : resp_headers,
                                "content"     : None
                            }
                            
                            # İçerik akışını başlat
                            content_type = resp_headers.get("Content-Type", "")
                            async for chunk in stream_video_content(response, decoded_url, content_type):
                                yield {"content": chunk}
                            
                    except httpx.RequestError as e:
                        error_msg = f"İstek hatası: {str(e)}"
                        konsol.print(error_msg)
                        yield await handle_errors(502, error_msg)
                    except httpx.TimeoutException as e:
                        error_msg = f"Zaman aşımı hatası: {str(e)}"
                        konsol.print(error_msg)
                        yield await handle_errors(504, error_msg)
                    except Exception as e:
                        error_msg = f"Beklenmeyen hata: {str(e)}"
                        konsol.print(error_msg)
                        konsol.print(traceback.format_exc())
                        yield await handle_errors(500, error_msg)
            except Exception as client_error:
                error_msg = f"HTTP istemci hatası: {str(client_error)}"
                konsol.print(error_msg)
                konsol.print(traceback.format_exc())
                yield await handle_errors(500, error_msg)
        
        # İlk yanıtı al
        stream_iter = stream_generator()
        first_yield = await stream_iter.__anext__()
        
        # Eğer içerik varsa, bu bir hata yanıtıdır
        if first_yield.get("content") is not None:
            return Response(
                content     = first_yield["content"],
                status_code = first_yield["status_code"],
                headers     = first_yield["headers"],
                media_type  = "text/plain"
            )
        
        # Normal yanıt için StreamingResponse hazırla
        status_code  = first_yield["status_code"]
        resp_headers = first_yield["headers"]
        
        elapsed = time.time() - start_time
        konsol.print(f"Proxy yanıtı başlatıldı: Status: {status_code}, {elapsed:.2f}s içinde")
        
        # İçerik filtreleme fonksiyonu
        async def content_generator():
            try:
                # İlk değeri zaten işledik, şimdi sadece içerik gönder
                async for item in stream_iter:
                    if "content" in item and item["content"] is not None:
                        yield item["content"]
            except Exception as gen_error:
                konsol.print(f"İçerik akışı hatası: {str(gen_error)}")
                konsol.print(traceback.format_exc())
                
        # Stream yanıtı döndür
        return StreamingResponse(
            content_generator(),
            status_code = status_code,
            headers     = resp_headers,
            media_type  = resp_headers.get("Content-Type", "video/mp4"),
        )
        
    except Exception as e:
        elapsed = time.time() - start_time
        konsol.print(f"Video proxy hatası ({elapsed:.2f}s): {str(e)}")
        konsol.print(traceback.format_exc())
        return Response(
            content     = f"Video proxy hatası: {str(e)}",
            status_code = 500,
            media_type  = "text/plain",
            headers     = CORS_HEADERS
        )


@home_router.get("/proxy/subtitle")
async def subtitle_proxy(request: Request, url: str, referer: str = None, headers: str = None):
    """Altyazı proxy endpoint'i - İyileştirilmiş"""
    try:
        # URL'i decode et
        decoded_url = unquote(url)
        
        # İstemci başlıklarını decode et
        decoded_headers = {}
        if headers:
            try:
                decoded_headers = json.loads(headers)
            except json.JSONDecodeError as e:
                konsol.print(f"Altyazı header parsing hatası: {str(e)}")
        
        # İstemciden gelen User-Agent bilgisini al
        user_agent = decoded_headers.get("User-Agent", DEFAULT_USER_AGENT)
        
        # Hedef sunucuya gönderilecek başlıkları ayarla
        client_headers = {
            "User-Agent"      : user_agent,
            "Accept"          : "*/*",
            "Accept-Encoding" : "identity",
            "Connection"      : "keep-alive",
        }
        
        # Referer bilgisi varsa ekle
        if referer:
            client_headers["Referer"] = unquote(referer)
        
        konsol.print(f"Altyazı proxy isteği: {decoded_url[:100]}...")
        
        # Altyazı içeriğini al ve işle
        try:
            async with await create_httpx_client() as client:
                response = await client.get(decoded_url, headers=client_headers, timeout=30.0)
                
                if response.status_code >= 400:
                    error_msg = f"Altyazı kaynağı {response.status_code} hatası döndürdü"
                    konsol.print(f"Altyazı hatası: {error_msg}")
                    return Response(
                        content     = error_msg,
                        status_code = response.status_code,
                        media_type  = "text/plain",
                        headers     = CORS_HEADERS
                    )
                
                content      = response.content
                content_type = response.headers.get("Content-Type", "")
                
                # VTT formatını düzeltme
                if "text/vtt" in content_type or any(content.startswith(prefix) for prefix in [b"WEBVTT", b"\xef\xbb\xbfWEBVTT"]):
                    # UTF-8 BOM kontrolü
                    if content.startswith(b"\xef\xbb\xbf"):
                        content = content[3:]  # BOM'u kaldır
                    
                    # WEBVTT başlığı kontrolü
                    if not content.startswith(b"WEBVTT"):
                        content = b"WEBVTT\n\n" + content
                
                # SRT formatını VTT'ye dönüştür
                elif content_type == "application/x-subrip" or decoded_url.endswith(".srt") or content.strip().startswith(b"1\r\n") or content.strip().startswith(b"1\n"):
                    try:
                        # SRT formatını VTT'ye dönüştür - basit bir yöntem
                        if not content.startswith(b"WEBVTT"):
                            # Yeni satır karakterlerini normalize et
                            content = content.replace(b"\r\n", b"\n")
                            # WEBVTT başlığı ekle
                            content = b"WEBVTT\n\n" + content
                            # Zaman formatını düzelt (,000 -> .000)
                            content = content.replace(b",", b".")
                    except Exception as srt_error:
                        konsol.print(f"SRT dönüştürme hatası: {str(srt_error)}")
        
        except httpx.RequestError as e:
            konsol.print(f"Altyazı istek hatası: {str(e)}")
            return Response(
                content     = f"Altyazı istek hatası: {str(e)}",
                status_code = 502,
                media_type  = "text/plain",
                headers     = CORS_HEADERS
            )
        except httpx.TimeoutException as e:
            konsol.print(f"Altyazı zaman aşımı: {str(e)}")
            return Response(
                content     = f"Altyazı zaman aşımı: {str(e)}",
                status_code = 504,
                media_type  = "text/plain",
                headers     = CORS_HEADERS
            )
        
        # CORS başlıklarını içeren yanıt başlıkları
        resp_headers = {
            "Content-Type": "text/vtt; charset=utf-8",
            **CORS_HEADERS
        }
        
        # Altyazı içeriğini döndür
        return Response(
            content     = content,
            status_code = 200,
            headers     = resp_headers,
            media_type  = "text/vtt",
        )
        
    except Exception as e:
        konsol.print(f"Altyazı proxy hatası: {str(e)}")
        konsol.print(traceback.format_exc())
        return Response(
            content     = f"Altyazı proxy hatası: {str(e)}",
            status_code = 500,
            media_type  = "text/plain",
            headers     = CORS_HEADERS
        )