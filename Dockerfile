# Use an official Python runtime as a parent image
FROM python:3.14.1-slim

# Set the working directory in the container
WORKDIR /usr/src/smtp-relay/

# Copy the requirements file into the container at /usr/src/smtp-relay/
COPY ./requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the src contents into the container
COPY ./src .

# Make port 8025 available to the world outside this container
EXPOSE 8025

# Run main.py when the container launches
CMD ["python", "main.py"]
