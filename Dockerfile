# Use an official Python runtime as a parent image
FROM python:3.14.3-slim

# Pinned UID/GID so host volumes and Kubernetes securityContexts can match
ARG UID=10001
ARG GID=10001

# Create an unprivileged user to run the relay
RUN groupadd --gid "${GID}" smtp-relay \
    && useradd --uid "${UID}" --gid "${GID}" --no-create-home --shell /usr/sbin/nologin smtp-relay

# Set the working directory in the container
WORKDIR /usr/src/smtp-relay/

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv

# Install locked dependencies into /opt/venv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/opt/venv/bin:$PATH"
COPY ./pyproject.toml ./uv.lock ./
RUN uv sync --frozen --no-dev

# Copy the src contents into the container
COPY ./src .

# Create the default certificate mount point and hand ownership to the relay user
RUN mkdir -p certs && chown -R "${UID}:${GID}" /usr/src/smtp-relay

# Run the relay as the unprivileged user
USER ${UID}:${GID}

# Make port 8025 available to the world outside this container
EXPOSE 8025

# Run main.py when the container launches
CMD ["python", "main.py"]
