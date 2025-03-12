# Use an official Python runtime as a parent image
FROM python:3.13-slim

# Set the working directory in the container
WORKDIR /usr/src/smtp-relay/

# Copy the current directory contents into the container
COPY . .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Make port 8025 available to the world outside this container
EXPOSE 8025

# Run main.py when the container launches
CMD ["python", "main.py"]
