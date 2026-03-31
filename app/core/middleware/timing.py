import time
import json
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.concurrency import iterate_in_threadpool
from starlette.responses import StreamingResponse

class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.perf_counter()
        response = await call_next(request)
        process_time = time.perf_counter() - start_time
        duration_ms = round(process_time * 1000, 2)
        
        # Inject duration_ms into application/json responses that have a 'meta' envelope block
        if response.headers.get("content-type") == "application/json":
            # Consume the response body stream
            response_body = [chunk async for chunk in response.body_iterator]
            response.body_iterator = iterate_in_threadpool(iter(response_body))
            body = b"".join(response_body)
            
            try:
                data = json.loads(body)
                if isinstance(data, dict) and "meta" in data:
                    data["meta"]["duration_ms"] = duration_ms
                    new_body = json.dumps(data).encode("utf-8")
                    
                    # Update content-length if modified
                    if "content-length" in response.headers:
                        response.headers["content-length"] = str(len(new_body))
                        
                    async def stream_wrapper():
                        yield new_body
                        
                    response.body_iterator = stream_wrapper()
            except Exception:
                # If parsing fails, just rebuild iterator and proceed normally
                async def original_wrapper():
                    for chunk in response_body:
                        yield chunk
                response.body_iterator = original_wrapper()
                
        return response
