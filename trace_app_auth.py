import sys
import trace

def trace_import():
    try:
        import app.api.auth
    except Exception as e:
        print("Exception:", e)

if __name__ == '__main__':
    tracer = trace.Trace(count=False, trace=True, ignoredirs=[sys.prefix, sys.exec_prefix])
    tracer.run('trace_import()')
