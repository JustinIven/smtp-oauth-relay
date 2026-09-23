# Docker Deployment

Mount a `certs/` directory containing `cert.pem` and `key.pem` (see [Manual install](manual.md#generate-a-self-signed-certificate-testing) to generate test certs), then run the relay on port `8025`.

!!! info "Runs as non-root"
    The image runs as the unprivileged user `smtp-relay` with a pinned **UID/GID `10001`**. Mounted certificates must be readable by that UID, e.g. `chown -R 10001:10001 certs` or `chmod o+r certs/*.pem`. Because the process is unprivileged it cannot bind ports below 1024 inside the container — publish a privileged host port instead (`-p 587:8025`).

=== "docker run"

    ```bash
    docker run --name smtp-relay -p 8025:8025 \
      -v $(pwd)/certs:/usr/src/smtp-relay/certs \
      -e TLS_SOURCE=file \
      -e REQUIRE_TLS=true \
      ghcr.io/justiniven/smtp-oauth-relay:1
    ```

=== "--env-file"

    `.env`:

    ```bash
    TLS_SOURCE=file
    REQUIRE_TLS=true
    SERVER_GREETING=My SMTP Relay
    ```

    ```bash
    docker run --name smtp-relay -p 8025:8025 \
      -v $(pwd)/certs:/usr/src/smtp-relay/certs \
      --env-file .env \
      ghcr.io/justiniven/smtp-oauth-relay:1
    ```

=== "docker compose"

    `docker-compose.yml`:

    ```yaml
    services:
      smtp-relay:
        image: ghcr.io/justiniven/smtp-oauth-relay:1
        container_name: smtp-oauth-relay
        ports:
          - "8025:8025"
        volumes:
          - ./certs:/usr/src/smtp-relay/certs
        environment:
          - TLS_SOURCE=file
          - REQUIRE_TLS=true
        restart: unless-stopped
    ```

    ```bash
    docker compose up -d
    docker compose logs -f smtp-relay
    ```

See the [configuration reference](../configuration.md) for all environment variables.

??? note "Change the UID/GID"
    The user is created at build time from the `UID`/`GID` build arguments:

    ```bash
    docker build --build-arg UID=1500 --build-arg GID=1500 -t smtp-oauth-relay:local .
    ```

    With the prebuilt image you can override the runtime user instead — the relay needs no write access, only read access to the certificates:

    ```bash
    docker run --name smtp-relay -p 8025:8025 --user 1500:1500 \
      -v $(pwd)/certs:/usr/src/smtp-relay/certs:ro \
      -e TLS_SOURCE=file ghcr.io/justiniven/smtp-oauth-relay:1
    ```

??? note "Build from source"
    ```bash
    git clone https://github.com/justiniven/smtp-oauth-relay.git
    cd smtp-oauth-relay
    docker build -t smtp-oauth-relay:local .
    docker run --name smtp-relay -p 8025:8025 \
      -v $(pwd)/certs:/usr/src/smtp-relay/certs \
      -e TLS_SOURCE=file smtp-oauth-relay:local
    ```

## Next steps

- [Configure the relay](../configuration.md)
- [Set up Entra ID](../entra-id-setup/index.md)
- [Configure your SMTP clients](../client-setup.md)
