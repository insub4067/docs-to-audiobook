# Use official light-weight Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /code

# Copy requirements file first for caching
COPY ./requirements.txt /code/requirements.txt

# Install dependencies
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Set up user 1000 for Hugging Face Space security requirements
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# Set working directory inside user home/app
WORKDIR $HOME/app

# Copy application files (preserving structure)
COPY --chown=user:user . $HOME/app

# Ensure uploads directory is present and writable
RUN mkdir -p $HOME/app/uploads && chmod -R 777 $HOME/app/uploads

# Expose Hugging Face Space default port
EXPOSE 7860

# Run FastAPI app with Uvicorn on port 7860
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
