FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY teacher_module ./teacher_module
COPY visual_director ./visual_director
COPY animation_engine ./animation_engine
COPY backend ./backend
COPY frontend ./frontend
RUN pip install --no-cache-dir -e ./teacher_module -e ./visual_director \
    -e "./animation_engine[speech]" -e ./backend
EXPOSE 8000
CMD ["uvicorn","weiguang_backend.main:app","--host","0.0.0.0","--port","8000"]
