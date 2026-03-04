import relay_logging


def test_relay_logging_helpers_cover() -> None:
    relay_logging.log_rejected_mail_from("bad")
    relay_logging.log_rejected_rcpt_to("bad")
    relay_logging.log_message_received("from", ["to"])
    relay_logging.log_missing_access_token()
    relay_logging.log_data_handler_exception(RuntimeError("boom"))
    relay_logging.log_server_started()
    relay_logging.log_server_start_failed(RuntimeError("boom"))
    relay_logging.log_shutdown_requested()
    relay_logging.log_unexpected_error(RuntimeError("boom"))
    relay_logging.log_shutting_down()
    relay_logging.log_oauth_token_request_failed(RuntimeError("boom"))
    relay_logging.log_oauth_token_response_details(500, "error")
    relay_logging.log_unsupported_auth_mechanism("XOAUTH2")
    relay_logging.log_missing_auth_data()
    relay_logging.log_auth_login_decode_failed(UnicodeDecodeError("utf-8", b"x", 0, 1, "bad"))
    relay_logging.log_auth_parse_failed("bad")
    relay_logging.log_authentication_failed(RuntimeError("boom"))
    relay_logging.log_auth_unexpected_error(RuntimeError("boom"))
    relay_logging.log_rate_limited("user@example.com")
