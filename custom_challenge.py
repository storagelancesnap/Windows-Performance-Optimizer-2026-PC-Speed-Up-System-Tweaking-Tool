import hashlib
import json
import random
import time
import instagrapi
from enum import Enum
from typing import Dict
from instagrapi.utils import dumps, generate_signature

import requests

from instagrapi.exceptions import (
    ChallengeError,
    ChallengeRedirection,
    ChallengeRequired,
    ChallengeSelfieCaptcha,
    ChallengeUnknownStep,
    LegacyForceSetNewPasswordForm,
    RecaptchaChallengeForm,
    SelectContactPointRecoveryForm,
    SubmitPhoneNumberForm,
)

WAIT_SECONDS = 5


class ChallengeChoice(Enum):
    SMS = 0
    EMAIL = 1


def extract_messages(challenge):
    messages = []
    for item in challenge["extraData"].get("content"):
        message = item.get("title", item.get("text"))
        if message:
            dot = "" if message.endswith(".") else "."
            messages.append(f"{message}{dot}")
    return messages


class ChallengeResolveMixin:

    def update(self, client : instagrapi.Client):
        self.client = client

    def challenge_resolve(self, last_json: Dict) -> bool:
        # START GET REQUEST to challenge_url
        challenge_url = last_json["challenge"]["api_path"]
        try:
            challenge_context = last_json.get("challenge", {}).get("challenge_context")
            if not challenge_context:
                user_id, nonce_code = challenge_url.split("/")[2:4]
                challenge_context = json.dumps(
                    {
                        "step_name": "",
                        "nonce_code": nonce_code,
                        "user_id": int(user_id),
                        "is_stateless": False,
                    }
                )
            params = {
                "guid": self.client.uuid,
                "device_id": self.client.android_device_id,
                "challenge_context": challenge_context,
            }
            
            if "challenge_node_id" in last_json["challenge"]["url"]:
                params |= {
                    "challenge_node_id": last_json["challenge"]["url"].split("challenge_node_id=")[-1]
                }
            
        except ValueError:
            # not enough values to unpack (expected 2, got 1)
            params = {}
        
        try:
            self.client._send_private_request(challenge_url[1:], params=params)
        except ChallengeRequired:
            assert self.client.last_json["message"] == "challenge_required", self.client.last_json
            return self.challenge_resolve_contact_form(challenge_url)
        return self.challenge_resolve_simple(challenge_url)

    def challenge_resolve_contact_form(self, challenge_url: str) -> bool:
        """
        Start challenge resolve

        Помогите нам удостовериться, что вы владеете этим аккаунтом
        > CODE
        Верна ли информация вашего профиля?
        Мы заметили подозрительные действия в вашем аккаунте.
        В целях безопасности сообщите, верна ли информация вашего профиля.
        > I AGREE

        Help us make sure you own this account
        > CODE
        Is your profile information correct?
        We have noticed suspicious activity on your account.
        For security reasons, please let us know if your profile information is correct.
        > I AGREE

        Parameters
        ----------
        challenge_url: str
            Challenge URL

        Returns
        -------
        bool
            A boolean value
        """
        result = self.client.last_json
        challenge_url = "https://i.instagram.com%s" % challenge_url
        enc_password = "#PWD_INSTAGRAM_BROWSER:0:%s:" % str(int(time.time()))
        instagram_ajax = hashlib.sha256(enc_password.encode()).hexdigest()[:12]
        session = requests.Session()
        session.verify = False  # fix SSLError/HTTPSConnectionPool
        session.proxies = self.client.private.proxies
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Linux; Android 8.0.0; MI 5s Build/OPR1.170623.032; wv) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/80.0.3987.149 "
                "Mobile Safari/537.36 %s" % self.client.user_agent,
                "upgrade-insecure-requests": "1",
                "sec-fetch-dest": "document",
                "accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/webp,image/apng,*/*;q=0.8,"
                    "application/signed-exchange;v=b3;q=0.9"
                ),
                "x-requested-with": "com.instagram.android",
                "sec-fetch-site": "none",
                "sec-fetch-mode": "navigate",
                "sec-fetch-user": "?1",
                "accept-encoding": "gzip, deflate",
                "accept-language": "en-US,en;q=0.9,en-US;q=0.8,en;q=0.7",
                "pragma": "no-cache",
                "cache-control": "no-cache",
            }
        )
        for key, value in self.client.private.cookies.items():
            if key in ["mid", "csrftoken"]:
                session.cookies.set(key, value)
        time.sleep(WAIT_SECONDS)
        result = session.get(challenge_url)  # render html form
        session.headers.update(
            {
                "x-ig-www-claim": "0",
                "x-instagram-ajax": instagram_ajax,
                "content-type": "application/x-www-form-urlencoded",
                "accept": "*/*",
                "sec-fetch-dest": "empty",
                "x-requested-with": "XMLHttpRequest",
                "x-csrftoken": session.cookies.get_dict().get("csrftoken"),
                "x-ig-app-id": self.client.private.headers.get("X-IG-App-ID"),
                "sec-fetch-site": "same-origin",
                "sec-fetch-mode": "cors",
                "referer": challenge_url,
            }
        )
        time.sleep(WAIT_SECONDS)
        choice = ChallengeChoice.EMAIL
        result = session.post(challenge_url, {"choice": choice})
        result = result.json()
        for retry in range(8):
            time.sleep(WAIT_SECONDS)
            try:
                # FORM TO ENTER CODE
                result = self.handle_challenge_result(result)
                break
            except SelectContactPointRecoveryForm as e:
                if choice == ChallengeChoice.SMS:  # last iteration
                    raise e
                choice = ChallengeChoice.SMS
                result = session.post(challenge_url, {"choice": choice})
                result = result.json()
                continue  # next choice attempt
            except SubmitPhoneNumberForm as e:
                result = session.post(
                    challenge_url,
                    {
                        "phone_number": e.challenge["fields"]["phone_number"],
                        "challenge_context": e.challenge["challenge_context"],
                    },
                )
                result = result.json()
                break
            except ChallengeRedirection:
                return True  # instagram redirect
        assert result.get("challengeType") in (
            "VerifyEmailCodeForm",
            "VerifySMSCodeForm",
            "VerifySMSCodeFormForSMSCaptcha",
        ), result
        for retry_code in range(5):
            for attempt in range(1, 11):
                code = self.client.challenge_code_handler(self.client.username, choice)
                if code:
                    break
                time.sleep(WAIT_SECONDS * attempt)
            # SEND CODE
            time.sleep(WAIT_SECONDS)
            result = session.post(challenge_url, {"security_code": code}).json()
            result = result.get("challenge", result)
            if (
                "Please check the code we sent you and try again"
                not in (result.get("errors") or [""])[0]
            ):
                break
        # FORM TO APPROVE CONTACT DATA
        challenge_type = result.get("challengeType")
        if challenge_type == "LegacyForceSetNewPasswordForm":
            self.challenge_resolve_new_password_form(result)
        assert result.get("challengeType") == "ReviewContactPointChangeForm", result
        details = []
        for data in result["extraData"]["content"]:
            for entry in data.get("labeled_list_entries", []):
                val = entry["list_item_text"]
                if "@" not in val:
                    val = val.replace(" ", "").replace("-", "")
                details.append(val)
        # CHECK ACCOUNT DATA
        for detail in [self.client.username, self.client.email, self.client.phone_number]:
            assert (
                not detail or detail in details
            ), 'ChallengeResolve: Data invalid: "%s" not in %s' % (detail, details)
        time.sleep(WAIT_SECONDS)
        result = session.post(
            "https://i.instagram.com%s" % result.get("navigation").get("forward"),
            {
                "choice": 0,  # I AGREE
                "enc_new_password1": enc_password,
                "new_password1": "",
                "enc_new_password2": enc_password,
                "new_password2": "",
            },
        ).json()
        assert result.get("type") == "CHALLENGE_REDIRECTION", result
        assert result.get("status") == "ok", result
        return True

    def challenge_resolve_new_password_form(self, result):
        msg = " ".join(
            [
                "Log into your Instagram account from smartphone and change password!",
                *extract_messages(result),
            ]
        )
        raise LegacyForceSetNewPasswordForm(msg)

    def handle_challenge_result(self, challenge: Dict):
        messages = []
        if "challenge" in challenge:
            challenge = challenge["challenge"]
        challenge_type = challenge.get("challengeType")
        if challenge_type == "SelectContactPointRecoveryForm":
            """
            Помогите нам удостовериться, что вы владеете этим аккаунтом
            Чтобы защитить свой аккаунт, запросите помощь со входом.
            {'message': '',
            'challenge': {'challengeType': 'SelectContactPointRecoveryForm',
            'errors': ['Select a valid choice. 1 is not one of the available choices.'],
            'experiments': {},
            'extraData': {'__typename': 'GraphChallengePage',
            'content': [{'__typename': 'GraphChallengePageHeader',
            'description': None,
            'title': 'Help Us Confirm You Own This Account'},
            {'__typename': 'GraphChallengePageText',
            'alignment': 'center',
            'html': None,
            'text': 'To secure your account, you need to request help logging in.'},
            {'__typename': 'GraphChallengePageForm',
            'call_to_action': 'Get Help Logging In',
            'display': 'inline',
            'fields': None,
            'href': 'https://help.instagram.com/358911864194456'}]},
            'fields': {'choice': 'None'},
            'navigation': {'forward': '/challenge/8530598273/PlWAX2OMVk/',
            'replay': '/challenge/replay/8530598273/PlWAX2OMVk/',
            'dismiss': 'instagram://checkpoint/dismiss'},
            'privacyPolicyUrl': '/about/legal/privacy/',
            'type': 'CHALLENGE'},
            'status': 'fail'}
            """
            if "extraData" in challenge:
                messages += extract_messages(challenge)
            if "errors" in challenge:
                for error in challenge["errors"]:
                    messages.append(error)
            raise SelectContactPointRecoveryForm(
                " ".join(messages), challenge=challenge
            )
        elif challenge_type == "RecaptchaChallengeForm":
            """
            Example:
            {'message': '',
            'challenge': {
            'challengeType': 'RecaptchaChallengeForm',
            'errors': ['Неправильная Captcha. Попробуйте еще раз.'],
            'experiments': {},
            'extraData': None,
            'fields': {'g-recaptcha-response': 'None',
            'disable_num_days_remaining': -60,
            'sitekey': '6LebnxwUAAAAAGm3yH06pfqQtcMH0AYDwlsXnh-u'},
            'navigation': {'forward': '/challenge/32708972491/CE6QdsYZyB/',
            'replay': '/challenge/replay/32708972491/CE6QdsYZyB/',
            'dismiss': 'instagram://checkpoint/dismiss'},
            'privacyPolicyUrl': '/about/legal/privacy/',
            'type': 'CHALLENGE'},
            'status': 'fail'}
            """
            print(self.client.last_json)
            raise RecaptchaChallengeForm(". ".join(challenge.get("errors", [])))
        elif challenge_type in ("VerifyEmailCodeForm", "VerifySMSCodeForm"):
            # Success. Next step
            return challenge
        elif challenge_type == "SubmitPhoneNumberForm":
            raise SubmitPhoneNumberForm(challenge=challenge)
        elif challenge_type:
            # Unknown challenge_type
            messages.append(challenge_type)
            if "errors" in challenge:
                messages.append("\n".join(challenge["errors"]))
            messages.append("(Please manual login)")
            raise ChallengeError(" ".join(messages))
        elif challenge.get("type") == "CHALLENGE_REDIRECTION":
            """
            Example:
            {'location': 'instagram://checkpoint/dismiss',
            'status': 'ok',
            'type': 'CHALLENGE_REDIRECTION'}
            """
            raise ChallengeRedirection()
        return challenge

    def challenge_resolve_simple(self, challenge_url: str) -> bool:
        step_name = self.client.last_json.get("step_name", "")
        if step_name == "delta_login_review" or step_name == "scraping_warning":
            self.client._send_private_request(challenge_url, {"choice": "0"})
            return True
        elif step_name == "add_birthday":
            random_year = random.randint(1970, 2004)
            random_month = random.randint(1, 12)
            random_day = random.randint(1, 28)
            self.client._send_private_request(
                challenge_url,
                {
                    "birthday_year": str(random_year),
                    "birthday_month": str(random_month),
                    "birthday_day": str(random_day),
                },
            )
            return True
        elif step_name in ("verify_email", "verify_email_code", "select_verify_method"):
            if step_name == "select_verify_method":
                """
                {'step_name': 'select_verify_method',
                'step_data': {'choice': '0',
                'fb_access_token': 'None',
                'big_blue_token': 'None',
                'google_oauth_token': 'true',
                'vetted_device': 'None',
                'phone_number': '+7 *** ***-**-09',
                'email': 'x****g@y*****.com'},     <------------- choice
                'nonce_code': 'DrW8V4m5Ec',
                'user_id': 12060121299,
                'status': 'ok'}
                """
                steps = self.client.last_json["step_data"].keys()
                challenge_url = challenge_url[1:]
                if "email" in steps:
                    self.client._send_private_request(
                        challenge_url, {"choice": ChallengeChoice.EMAIL}
                    )
                elif "phone_number" in steps:
                    self.client._send_private_request(
                        challenge_url, {"choice": ChallengeChoice.SMS}
                    )
                else:
                    raise ChallengeError(
                        f'ChallengeResolve: Choice "email" or "phone_number" '
                        f"(sms) not available to this account {self.client.last_json}"
                    )
            wait_seconds = 5
            for attempt in range(2):
                code = self.client.challenge_code_handler(self.client.username, ChallengeChoice.EMAIL)
                if code:
                    break
                time.sleep(wait_seconds)
            # print(
            #     f'Code entered "{code}" for {self.client.username} ({attempt} attempts by {wait_seconds} seconds)'
            # )
            self.client._send_private_request(challenge_url, {"security_code": code})
            # assert 'logged_in_user' in client.last_json
            assert self.client.last_json.get("action", "") == "close"
            assert self.client.last_json.get("status", "") == "ok"
            return True
        elif step_name == "":
            assert self.client.last_json.get("action", "") == "close"
            assert self.client.last_json.get("status", "") == "ok"
            return True
        elif step_name == "change_password":
            # Example: {'step_name': 'change_password',
            #  'step_data': {'new_password1': 'None', 'new_password2': 'None'},
            #  'flow_render_type': 3,
            #  'bloks_action': 'com.instagram.challenge.navigation.take_challenge',
            #  'cni': 18226879502000588,
            #  'challenge_context': '{"step_name": "change_password",
            #      "cni": 18226879502000588, "is_stateless": false,
            #      "challenge_type_enum": "PASSWORD_RESET"}',
            #  'challenge_type_enum_str': 'PASSWORD_RESET',
            #  'status': 'ok'}
            wait_seconds = 5
            for attempt in range(24):
                pwd = self.client.change_password_handler(self.client.username)
                if pwd:
                    break
                time.sleep(wait_seconds)
            print(
                f'Password entered "{pwd}" for {self.client.username} ({attempt} attempts by {wait_seconds} seconds)'
            )
            return self.client.bloks_change_password(pwd, self.client.last_json["challenge_context"])
        elif step_name == "selfie_captcha":
            print(self.client.last_json)
            raise ChallengeSelfieCaptcha(self.client.last_json)
        elif step_name == "dummy_step":
            # com.bloks.www.ixt.gateway.clear
            # {
            #     "step_name": "dummy_step",
            #     "step_data": {
            #         "screen_data": "{'screen_output_payload':{}}",
            #         "actor_gateway_enrollment_id": "1122589376154184"
            #     },
            #     "flow_render_type": 7,
            #     "bloks_action": "com.bloks.www.ig.ixt.trigger.enrollment",
            #     "cni": 17884790490153043,
            #     "challenge_context": "Af5MlbElDZlPJrWdSOXvj-6NikIdLrGIBAf5k_4YQKBq1xQn7WDeKDESfwAKhe4vQE3HyZt6QpRgg3oUm3fuuLyzCWrP_XJ72QEZdz9CSPeqWvfsAId_lIpRybBvr-d3S7Q_3e-GSDE90vd05Q2pqBUza9iSNNLEraeh1pXbdeYzEKxmvIY0AftFhZkCqshi-ZN8cXnuyNCECsEIFZNm0AatAi-AsazYDGE542zuGF9OfEq17_0rNPIIQg",
            #     "challenge_type_enum_str": "DELETED_CONTENT",
            #     "actor_gateway_enrollment_id": 1122589376154184,
            #     "status": "ok"
            # }
            
            # data = self.client.with_default_data({
            #     # "params": dumps(
            #     #     {"client_input_params": {}, "server_params": {}}
            #     # ),
            #     "bk_client_context": dumps(
            #         {"bloks_version": self.client.bloks_versioning_id, "styles_id": "instagram"}
            #     ),
            #     "bloks_versioning_id": self.client.bloks_versioning_id,
            # })
            # self.client.private.headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
            # res = self.client.private.post(f"https://b.i.instagram.com/api/v1/bloks/apps/com.bloks.www.ixt.gateway.clear/", data=data, proxies=self.client.private.proxies)
            # print(f"Skip status: {res.status_code}, Body: {res.text}")
            self.client._send_private_request(challenge_url, {"choice": "0"})
            #print("dummy_step")
            return True
        elif step_name == "select_contact_point_recovery":
            """
            {
                'step_name': 'select_contact_point_recovery',
                'step_data': {'choice': '0',
                    'phone_number': '+62 ***-****-**11',
                    'email': 'g*******b@w**.de',
                    'hl_co_enabled': False,
                    'sigp_to_hl': False
                },
                'flow_render_type': 3,
                'bloks_action': 'com.instagram.challenge.navigation.take_challenge',
                'cni': 178623487724,
                'challenge_context': '{"step_name": "select_contact_point_recovery",
                "cni": 178623487724,
                "is_stateless": false,
                "challenge_type_enum": "HACKED_LOCK",
                "present_as_modal": false}',
                'challenge_type_enum_str': 'HACKED_LOCK',
                'status': 'ok'
            }
            """
            steps = self.client.last_json["step_data"].keys()
            challenge_url = challenge_url[1:]
            if "email" in steps:
                self.client._send_private_request(
                    challenge_url, {"choice": ChallengeChoice.EMAIL}
                )
            elif "phone_number" in steps:
                self.client._send_private_request(
                    challenge_url, {"choice": ChallengeChoice.SMS}
                )
            else:
                raise ChallengeError(
                    f'ChallengeResolve: Choice "email" or "phone_number" (sms) '
                    f"not available to this account {self.client.last_json}"
                )
            wait_seconds = 5
            for attempt in range(24):
                code = self.client.challenge_code_handler(self.client.username, ChallengeChoice.EMAIL)
                if code:
                    break
                time.sleep(wait_seconds)
            # print(
            #     f'Code entered "{code}" for {self.client.username} ({attempt} attempts by {wait_seconds} seconds)'
            # )
            self.client._send_private_request(challenge_url, {"security_code": code})

            if self.client.last_json.get("action", "") == "close":
                assert self.client.last_json.get("status", "") == "ok"
                return True

            assert (
                self.client.last_json["step_name"] == "review_contact_point_change"
            ), f"Unexpected step_name {self.client.last_json['step_name']}"

            # details = self.last_json["step_data"]

            # TODO: add validation of account details
            # assert self.username == details['username'], \
            #     f"Data invalid: {self.username} does not match {details['username']}"
            # assert self.email == details['email'], \
            #     f"Data invalid: {self.email} does not match {details['email']}"
            # assert self.phone_number == details['phone_number'], \
            #     f"Data invalid: {self.phone_number} does not match {details['phone_number']}"

            # "choice": 0 ==> details look good
            self.client._send_private_request(challenge_url, {"choice": 0})

            # TODO: assert that the user is now logged in.
            # # assert 'logged_in_user' in client.last_json
            # assert self.last_json.get("action", "") == "close"
            # assert self.last_json.get("status", "") == "ok"
            return True
        else:
            raise ChallengeUnknownStep(
                f'ChallengeResolve: Unknown step_name "{step_name}" for '
                f'"{self.client.username}" in challenge resolver: {self.client.last_json}'
            )
        return True
