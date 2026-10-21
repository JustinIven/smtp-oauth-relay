# Use the Chainguard Wolfi base image
FROM cgr.dev/chainguard/wolfi-base:latest

# Install Python 3.14 from the Wolfi repository; only the minor version stream is pinned
RUN apk add --no-cache python-3.14

# Set the working directory in the container
WORKDIR /usr/src/smtp-relay/

# Create a virtual environment for the application dependencies
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"
RUN python3.14 -m venv "${VIRTUAL_ENV}"

# Copy the requirements file into the container at /usr/src/smtp-relay/
COPY ./requirements.txt .

# Install any needed packages specified in requirements.txt, then drop pip from the runtime image
RUN pip install --no-cache-dir -r requirements.txt \
    && pip uninstall -y pip

# Copy the src contents into the container
COPY ./src .

# Make port 8025 available to the world outside this container
EXPOSE 8025

# Run main.py when the container launches
CMD ["python", "main.py"]
