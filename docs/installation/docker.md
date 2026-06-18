# Docker Deployment

Mount a `certs/` directory containing `cert.pem` and `key.pem` (see [Manual install](manual.md#generate-a-self-signed-certificate-testing) to generate test certs), then run the relay on port `8025`.

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
