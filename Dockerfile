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

# Copy the requirements file into the container at /usr/src/smtp-relay/
COPY ./requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

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
