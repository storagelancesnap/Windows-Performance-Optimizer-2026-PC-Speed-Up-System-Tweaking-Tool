from instagrapi import Client
from instagrapi.exceptions import ChallengeRequired, ChallengeUnknownStep
from instagrapi.utils import json_value
import random, requests, string, time, json, urllib, urllib.parse, uuid, mimetypes, os, datetime, sqlite3, multiprocessing, custom_challenge, traceback
from settings import Settings
from colorama import Fore
import telebot
from PIL import Image
from anticaptchaofficial.recaptchav2proxyless import recaptchaV2Proxyless
from mobiles import DEVICES
from requests.structures import CaseInsensitiveDict

class LogoutException(Exception): pass
class AccountSuspendedException(Exception): pass
class SubmitPhoneException(Exception): pass
class InfiniteSolveChallenge(Exception): pass

BASE_URL = "https://i.instagram.com/api/v1"
POST_URL_TEXTONLY = BASE_URL + "/media/configure_text_only_post/"
POST_URL_IMAGE = BASE_URL + "/media/configure_text_post_app_feed/"
POST_URL_SIDECAR = BASE_URL + "/media/configure_text_post_app_sidecar/"

class IAMParser:

    @staticmethod
    def parse(text) -> dict:
        useragent = text.split("|")[1]
        uuids = text.split("|")[2]
        cookies = urllib.parse.unquote(text.split("|")[3]).split(";")
        cookies = [cookie for cookie in cookies if len(cookie) > 0]
        cookies = {cookie.split("=", 1)[0].strip(): cookie.split("=", 1)[1].strip() for cookie in cookies if "=" in cookie}

        data = {
            "uuid": {
                "android_device_id": uuids.split(";")[0],
                "phone_id": uuids.split(";")[1],
                "uuid": uuids.split(";")[2],
                "advertising_id": uuids.split(";")[3],
            },
            "cookies": cookies,
        }

        if len(useragent) > 0:
            data |= {
                "user-agent": useragent,
                "device": {
                    "app_version": useragent.split(" ")[1],
                    "android_version": int(useragent.split("(", 1)[1].split(";")[0].split("/")[0]),
                    "android_release": useragent.split("(", 1)[1].split(";")[0].split("/")[1] + ".0.0",
                    "dpi": useragent.split("(", 1)[1].split(";")[1].strip(),
                    "resolution": useragent.split("(", 1)[1].split(";")[2].strip(),
                    "manufacturer": useragent.split("(", 1)[1].split(";")[3].strip(),
                    "device": useragent.split("(", 1)[1].split(";")[4].strip(),
                    "model": useragent.split("(", 1)[1].split(";")[5].strip(),
                    "cpu": useragent.split("(", 1)[1].split(";")[6].strip(),
                    "version_code": useragent.split("(", 1)[1].split(";")[7].strip(),
                }
            }

        return data

class Asocks:
    
    def __init__(self, key):
        self.key = key
        self.url = "https://api.asocks.com"
        self.session = requests.Session()
        
    def create_port(self, country_code: str, state: str, city: str, asn: int, type_id: int, proxy_type_id: int, name: None, server_port_type_id: int, count: int) -> str:
        res = self.session.post(self.url + "/v2/proxy/create-port", params={"apiKey": self.key}, json={
            "country_code": country_code,
            "state": state,
            "city": city,
            "type_id": type_id,
            "proxy_type_id": proxy_type_id,
            "name": None,
            "server_port_type_id": server_port_type_id,
            "count": count
        }).json()
        return f"socks5://{res['data'][0]['login']}:{res['data'][0]['password']}@{res['data'][0]['server']}:{res['data'][0]['port']}", res['data'][0]['id']
    
    def delete_port(self, id: int):
        res = self.session.delete(self.url + "/v2/proxy/delete-port", params={"id": id, "apiKey": self.key}).json()
        return res
    
    def dir_countries(self):
        res = self.session.get(self.url + "/v2/dir/countries", params={"apiKey": self.key}).json()
        return res["countries"]
    
    def dir_states(self, country_id: int | str):
        if str(country_id) == "-1": return []
        
        res = self.session.get(self.url + "/v2/dir/states", params={"apiKey": self.key, "countryId": country_id}).json()
        return res["states"]
    
    def dir_cities(self, country_id: int | str, state_id: int | str):
        if str(country_id) == "-1" or str(state_id) == "-1": return []
        
        res = self.session.get(self.url + "/v2/dir/cities", params={"apiKey": self.key, "countryId": country_id, "stateId": state_id}).json()
        return res["cities"]
    
    def dir_asns(self, country_id: int | str, state_id: int | str, city_id: int | str):
        if str(country_id) == "-1" or str(state_id) == "-1" or str(city_id) == "-1": return []

        res = self.session.get(self.url + "/v2/dir/asns", params={"apiKey": self.key, "countryId": country_id, "stateId": state_id, "cityId": city_id}).json()
        return res["asns"]["data"]

class Logger:

    @staticmethod
    def Log(text, color):
        print(f"[{Fore.CYAN}{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Fore.RESET}] {color}{text}{Fore.RESET}")
        try:
            with open("C:/Threads/logs.txt", "a") as f:
                f.write(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {text}\n")
        except Exception: pass

    @staticmethod
    def LogFile(text):
        try:
            with open("C:/Threads/logs.txt", "a") as f:
                f.write(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {text}\n")
        except Exception: pass

class Threads():
        
    def __init__(self, proxy: str | None = None, key: str = "", thread_index: int = 0, serialized_settings: str = ""):
        self.auth_session = requests.Session()
        self.proxy = proxy
        if proxy is not None:
            self.auth_session.proxies = {"http": proxy, "https": proxy}
        self.token = ""
        self.thread_index = thread_index
        self.key = key
        self.unique_settings = Settings(serialized_settings)
        self.last_response = None
        self.user_id = 0
        self.cl = Client(proxy=proxy)
        self.global_extra_header = {}
        
        device = random.choice(DEVICES)
        self.cl.set_device({
            "app_version": "269.0.0.18.75",
            "android_version": int(device.get("os_api", "26")),
            "android_release": device.get("os_version", "8.0.0"),
            "dpi": f"{device.get('dpi', '480')}dpi",
            "resolution": device.get("resolution_width", "1080") + "x" + device.get("resolution_height", "2400"),
            "manufacturer": device.get("device_brand", "OnePlus"),
            "device": device.get("device", "devitron"),
            "model": device.get("device_type", "6T Dev"),
            "cpu": device.get("proc_name", "qcom"),
            "version_code": "314665256",
        }, True)
        self.cl.set_user_agent(None, True)
        
        self.settings = {}
        self.challenge = custom_challenge.ChallengeResolveMixin()
        self.battery_level = random.randint(30, 80)

    def generate_headers(self, extra = {}):
        next_year = time.time() + 31536000
        headers = CaseInsensitiveDict({
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": "Barcelona 289.0.0.77.109 Android",
        })
        
        if self.token != "": headers["Authorization"] = f"Bearer IGT:2:{self.token}"

        headers.update(CaseInsensitiveDict(self.global_extra_header))
        headers.update(extra)
        
        return headers

    def post_private_request(self, url, params, headers, body, retry: bool = False):
        headers["Host"] = BASE_URL.split("//")[1].split("/")[0]
        if "rupload_igphoto" not in url:
            Logger.LogFile("=============================================================")
            Logger.LogFile(f"[thread#{self.thread_index}] POST {url}" + (f"?{urllib.parse.urlencode(params)}" if params is not None else ""))
            Logger.LogFile(f"[thread#{self.thread_index}] Headers={headers}")
            Logger.LogFile(f"[thread#{self.thread_index}] Body={body}")
        for i in range(5):
            try:
                r = self.auth_session.post(url, params=params, headers=headers, data=body)
                break
            except Exception: pass
        self.last_response = r
        if "rupload_igphoto" not in url:
            Logger.LogFile(f"[thread#{self.thread_index}] Response={r.text}")
        
        if "not-logged-in" in r.text or "no-js" in r.text or "login_required" in r.text:
            raise LogoutException()
        if "https://www.instagram.com/accounts/suspended/" in r.text:
            raise AccountSuspendedException()
        
        if r.headers.get("ig-set-x-mid", False):
            self.cl.mid = r.headers.get("ig-set-x-mid")
        
        if "challenge_required" in r.text and not retry:
            Logger.Log(f"[thread#{self.thread_index}] Begin solve /challenge/", Fore.YELLOW)
            try:
                self.challenge.update(self.cl)
                self.challenge.challenge_resolve(r.json())
            except ChallengeUnknownStep as e:
                if "sumbit_phone" in self.cl.last_json.get("step_name", ""): raise SubmitPhoneException()
            except Exception as e:
                Logger.Log(f"[thread#{self.thread_index}] {repr(e)}", Fore.YELLOW)
                raise LogoutException(self.cl.last_json)
            Logger.Log(f"[thread#{self.thread_index}] End solve /challenge/", Fore.YELLOW)
            
            if self.cl.last_json.get("action", "") == "close": time.sleep(random.uniform(3, 5))
            
            if "challenge" in self.cl.last_json and self.key != "" and self.cl.last_json["challenge"]["url"] == "https://i.instagram.com/challenge/":
                Logger.Log(f"[thread#{self.thread_index}] Trying solve captcha", Fore.YELLOW)
                captcha_info = requests.get("https://www.fbsbx.com/captcha/recaptcha/iframe/?compact=0&referer=https%3A%2F%2Fi.instagram.com&locale=en_US&__cci=ig_captcha_iframe", headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                    "Accept-Encoding": "gzip",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Host": "www.fbsbx.com",
                    "sec-ch-ua": '"Android WebView";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                    "sec-ch-ua-mobile": "?1",
                    "sec-ch-ua-platform": "Android",
                    "Sec-Fetch-Dest": "iframe",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "cross-site",
                    "Upgrade-Insecure-Requests": "1",
                    "User-Agent": self.cl.user_agent,
                    "X-Requested-With": "com.instagram.barcelona"
                })
                sitekey = captcha_info.text.split('data-sitekey="')[1].split('"')[0]
                
                g_recaptcha_response = self.wait_for_captcha(sitekey, "https://www.fbsbx.com/")
                self.post_private_request("https://i.instagram.com/api/v1/challenge/web/action/", None, self.generate_headers(), urllib.parse.urlencode({"g-recaptcha-response": g_recaptcha_response, "next": url.split("instagram.com")[1]}))
            
            return self.post_private_request(url, params, headers, body, True)
        if "challenge_required" in r.text and retry:
            raise InfiniteSolveChallenge(self.cl.last_json)
        
        return r
    
    def get_private_request(self, url, params, headers, retry: bool = False):
        headers["Host"] = BASE_URL.split("//")[1].split("/")[0]
        Logger.LogFile("=============================================================")
        Logger.LogFile(f"[thread#{self.thread_index}] GET {url}" + (f"?{urllib.parse.urlencode(params)}" if params is not None else ""))
        Logger.LogFile(f"[thread#{self.thread_index}] Headers={headers}")
        for i in range(5):
            try:
                r = self.auth_session.get(url, params=params, headers=headers)
                break
            except Exception: pass
        self.last_response = r
        Logger.LogFile(f"[thread#{self.thread_index}] Response={r.text}")
        
        if "not-logged-in" in r.text or "no-js" in r.text or "login_required" in r.text:
            raise LogoutException()
        if "https://www.instagram.com/accounts/suspended/" in r.text:
            raise AccountSuspendedException()
        
        if r.headers.get("ig-set-x-mid", False):
            self.cl.mid = r.headers.get("ig-set-x-mid")
        
        if "challenge_required" in r.text and not retry:
            Logger.Log(f"[thread#{self.thread_index}] Begin solve /challenge/", Fore.YELLOW)
            try:
                self.challenge.update(self.cl)
                self.challenge.challenge_resolve(r.json())
            except ChallengeUnknownStep as e:
                if "sumbit_phone" in self.cl.last_json.get("step_name", ""): raise SubmitPhoneException()
            except Exception as e:
                Logger.Log(f"[thread#{self.thread_index}] {repr(e)}", Fore.YELLOW)
                raise LogoutException(self.cl.last_json)
            Logger.Log(f"[thread#{self.thread_index}] End solve /challenge/", Fore.YELLOW)
            
            if self.cl.last_json.get("action", "") == "close": time.sleep(random.uniform(3, 5))
            
            if "challenge" in self.cl.last_json and self.key != "" and self.cl.last_json["challenge"]["url"] == "https://i.instagram.com/challenge/":
                Logger.Log(f"[thread#{self.thread_index}] Trying solve captcha", Fore.YELLOW)
                captcha_info = requests.get("https://www.fbsbx.com/captcha/recaptcha/iframe/?compact=0&referer=https%3A%2F%2Fi.instagram.com&locale=en_US&__cci=ig_captcha_iframe", headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                    "Accept-Encoding": "gzip",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Host": "www.fbsbx.com",
                    "sec-ch-ua": '"Android WebView";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                    "sec-ch-ua-mobile": "?1",
                    "sec-ch-ua-platform": "Android",
                    "Sec-Fetch-Dest": "iframe",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "cross-site",
                    "Upgrade-Insecure-Requests": "1",
                    "User-Agent": self.cl.user_agent,
                    "X-Requested-With": "com.instagram.barcelona"
                })
                sitekey = captcha_info.text.split('data-sitekey="')[1].split('"')[0]
                
                g_recaptcha_response = self.wait_for_captcha(sitekey, "https://www.fbsbx.com/")
                self.post_private_request("https://i.instagram.com/api/v1/challenge/web/action/", None, self.generate_headers(), urllib.parse.urlencode({"g-recaptcha-response": g_recaptcha_response, "next": url.split("instagram.com")[1]}))
            
            return self.get_private_request(url, params, headers, True)
        if "challenge_required" in r.text and retry:
            raise InfiniteSolveChallenge(self.cl.last_json)
        
        return r
    
    def is_avatar_set(self):
        return self.get_private_request("https://b.i.instagram.com/api/v1/multiple_accounts/get_account_family/", None, self.generate_headers()).json().get("current_account", {}).get("profile_pic_id", "") != ""

    def set_text_post_app_onboarding(self):
        body = urllib.parse.urlencode({
            "_uuid": self.cl.uuid,
            "waterfall_id": str(uuid.uuid4()),
            "profile_info": '{"bio":"","bio_links":[{"title":"","url":""}],"copy_profile_pic":false,"is_private":false}',
            "follower_info": '{"follow_ids":[],"is_follow_list":true}'
        })
        return self.post_private_request("https://i.instagram.com/api/v1/text_feed/set_text_post_app_onboarding/", None, self.generate_headers(), body).json()
    
    def wait_for_captcha(self, sitekey, websiteUrl):
        solver = recaptchaV2Proxyless()
        solver.set_verbose(1)
        solver.set_key(self.key)
        solver.set_website_url(websiteUrl)
        solver.set_website_key(sitekey)
        
        return solver.solve_and_return_solution()
    
    def login(self, username, password, email, email_password, relogin: bool = False):
        if relogin:
            self.cl = Client(proxy=self.proxy)
            #self.cl.set_device(self.generate_device_settings_signup(), True)
        
        def challenge_code_handler(username, choice):
            time.sleep(3)
            if choice == custom_challenge.ChallengeChoice.EMAIL:
                code = ""
                for _ in range(5):
                    code = "" # TODO: IMAP integration
                    Logger.Log(f"[thread#{self.thread_index}] Code received '{code}' from mail '{email}:{email_password}' ({_+1}/5)", Fore.YELLOW)
                    if len(code) == 6: return code
                    
                return False
            return False
        
        def handle_exception(client, exception):
            if isinstance(exception, ChallengeRequired):
                self.challenge.update(client)
                return self.challenge.challenge_resolve(client.last_json)
            raise exception
                
        try:
            self.cl.challenge_code_handler = challenge_code_handler
            self.cl.change_password_handler = lambda username: password
            self.cl.handle_exception = handle_exception
            self.cl.login(username, password)
            
            self.user_id = self.cl.user_info_by_username_v1(username).pk
            
            self.token = self.cl.private.headers["Authorization"].split("Bearer IGT:2:")[1]
        except ChallengeRequired as e:
            if repr(e) != "ChallengeRequired('challenge_required')" or self.key == "" or self.cl.last_json["challenge"]["url"] == "https://www.instagram.com/accounts/suspended/":
                Logger.Log(f"[thread#{self.thread_index}] Login error {repr(e)} | {self.cl.last_json}", Fore.RED)
                return False
            
            try:
                self.cl.bloks_action("com.bloks.www.caa.login.save-credentials", {
                    "offline_experiment_group": "caa_iteration_v3_perf_ig_4",
                    "_uuid": self.cl.uuid,
                    "family_device_id": self.cl.phone_id,
                    "bk_client_context": '{"bloks_version":"' + self.cl.bloks_versioning_id + '","styles_id":"instagram"}',
                    "bloks_versioning_id": self.cl.bloks_versioning_id
                })
            except Exception: pass
            
            captcha_info = requests.get("https://www.fbsbx.com/captcha/recaptcha/iframe/", headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Encoding": "gzip",
                "Accept-Language": "en-US,en;q=0.9",
                "Host": "www.fbsbx.com",
                "sec-ch-ua": '"Android WebView";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                "sec-ch-ua-mobile": "?1",
                "sec-ch-ua-platform": "Android",
                "Sec-Fetch-Dest": "iframe",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "cross-site",
                "Upgrade-Insecure-Requests": "1",
                "User-Agent": self.cl.user_agent,
                "X-Requested-With": "com.instagram.barcelona"
            }, params={"compact": "0", "referer": self.cl.last_json["challenge"]["url"], "locale": "en_US", "__cci": "ig_captcha_iframe"})
            sitekey = captcha_info.text.split('data-sitekey="')[1].split('"')[0]
            
            g_recaptcha_response = self.wait_for_captcha(sitekey, "https://www.fbsbx.com/")
            
            try:
                self.cl.private_request("challenge/web/action/", {"g-recaptcha-response": g_recaptcha_response, "challenge_node_id": self.cl.last_json["challenge"]["url"].split("=")[-1]}, with_signature=False)
            except Exception: pass
            
            self.token = self.cl.private.headers["Authorization"].split("Bearer IGT:2:")[1]
            
            return True
        except ChallengeUnknownStep as e:
            if "sumbit_phone" in self.cl.last_json.get("step_name", ""): raise SubmitPhoneException()
        except Exception as e:
            Logger.Log(f"[thread#{self.thread_index}] Login error {repr(e)}", Fore.RED)
            return False
        
        return True
    
    def get_post_by_url(self, url: str):
        return self.get_private_request("https://i.instagram.com/api/v1/text_feed/link_preview/", {"url": url}, self.generate_headers()).json()

    def _upload_image(self, path: str, is_avatar: bool = False):
        if self.unique_settings.unique_photo == 0 and not is_avatar:
            dist_path = path.replace(".", f"{''.join(random.choices(string.ascii_letters, k=8))}.")
            # TODO: Unique
            path = dist_path
        
        random_number = random.randint(1000000000, 9999999999)
        upload_id = int(time.time() * 1000)
        upload_name = f"{upload_id}_0_{random_number}"

        file_data = None
        file_length = None
        mime_type = "image/jpeg"
        waterfall_id = str(uuid.uuid4())

        is_url = path.startswith("http")
        is_file_path = not path.startswith("http")

        if is_file_path:
            with open(path, 'rb') as file:
                file_data = file.read()
                file_length = len(file_data)

        mime_type = mimetypes.guess_type(path)[0]

        if is_url:
            response = requests.get(path).content

            file_data = response
            file_length = len(response)

        parameters_as_string = {
            "media_type": 1,
            "upload_id": str(upload_id),
            "sticker_burnin_params": json.dumps([]),
            "image_compression": json.dumps(
                {
                    "lib_name": "moz",
                    "lib_version": "3.1.m",
                    "quality": "80",
                },
            ),
            "xsharing_user_ids": json.dumps([]),
            "retry_context": json.dumps(
                {
                    "num_step_auto_retry": "0",
                    "num_reupload": "0",
                    "num_step_manual_retry": "0",
                },
            ),
            "IG-FB-Xpost-entry-point-v2": "feed",
        }

        headers = self.generate_headers({
            "Accept-Encoding": "gzip",
            "X-Instagram-Rupload-Params": json.dumps(parameters_as_string),
            "X_FB_PHOTO_WATERFALL_ID": waterfall_id,
            "X-Entity-Type": mime_type,
            "Offset": "0",
            "X-Entity-Name": upload_name,
            "X-Entity-Length": str(file_length),
            "Content-Type": "application/octet-stream",
            "Content-Length": str(file_length),
        })

        res = self.post_private_request("https://www.instagram.com/rupload_igphoto/" + upload_name, None, headers, file_data).json()
        
        if self.unique_settings.unique_photo == 0 and not is_avatar:
            os.remove(path)
        
        if res['status'] == 'ok':
            return res
        return None
    
    def get_views(self, post_id: str | int) -> int:
        return int(self.post_private_request("https://i.instagram.com/graphql/query", None, self.generate_headers(), {
            "method": "post",
            "pretty": "false",
            "format": "json",
            "server_timestamps": "true",
            "locale": "user",
            "fb_api_req_friendly_name": "PostLiveMetricsQuery",
            "client_doc_id": "88872704915828488118363430539",
            "enable_canonical_naming": "true",
            "enable_canonical_variable_overrides": "true",
            "enable_canonical_naming_ambiguous_type_prefixing": "true",
            "variables": '{"post_ids":["' + str(post_id) + '"]}'
        }).text.split('"impression_count":')[1].split("}")[0])

    def users_search(self, query: str):
        return self.get_private_request(f"{BASE_URL}/users/search/?q={query}", None, self.generate_headers()).json()
    
    def follow_user(self, user_id: str):
        return self.post_private_request(f"{BASE_URL}/friendships/create/{user_id}/", None, self.generate_headers(), None).json()
    
    def fbsearch_text_app_serp(self, query: str, recent: int | str = 0, rank_token: str | None = None, page_token: str | None = None, is_from_pull_to_refresh: bool = False):
        param = {
            "search_surface": "search_tab_typeahead",
            "recent": str(recent),
            "query": query,
            "is_from_pull_to_refresh": "0"
        }
        
        if rank_token is not None and page_token is not None and not is_from_pull_to_refresh:
            param |= {"rank_token": rank_token, "page_token": page_token}
            
        if is_from_pull_to_refresh: param |= {"is_from_pull_to_refresh": "1"}
        
        return self.get_private_request("https://i.instagram.com/api/v1/fbsearch/text_app/serp/", param, self.generate_headers()).json()
    
    def get_timeline(self, max_id: str | None = None, is_pull_to_refresh: bool = False):
        self.settings = self.cl.get_settings()
        payload = {
            "has_camera_permission": "1",
            "phone_id": self.cl.phone_id,
            "battery_level": self.battery_level,
            "timezone_offset": str(self.settings["timezone_offset"]),
            "pagination_source": "text_post_feed_threads",
            "device_id": self.cl.uuid,
            "request_id": str(uuid.uuid4()),
            "_uuid": self.cl.uuid,
            "reason": "pagination",
            "is_pull_to_refresh": "0",
            "push_disabled": "false",
            "is_charging": "0",
            "is_dark_mode": "0",
            "will_sound_on": "0",
            "bloks_versioning_id": self.cl.bloks_versioning_id
        }
        if is_pull_to_refresh: payload |= {"is_pull_to_refresh": "1", "reason": "pull_to_refresh"}
        else:
            if max_id is not None: payload |= {"max_id": max_id}
            else: payload |= {"reason": "cold_start_fetch"}
        
        return self.post_private_request(f"{BASE_URL}/feed/text_post_app_timeline/", None, self.generate_headers(), payload).json()
    
    def post(self, caption: str, image_path: list | str | None = None, url: str | None = None, parent_post_id: str | None = None, quoted_post_id: str | None = None, disable_comments: bool = False):
        self.settings = self.cl.get_settings()
        
        params = {
            "text_post_app_info": {"reply_control": 0 if not disable_comments else 1},
            "timezone_offset": str(self.settings["timezone_offset"]),
            "source_type": "4",
            "_uid": self.user_id,
            "device_id": self.settings["uuids"]["uuid"],
            "caption": caption,
            "upload_id": str(int(time.time() * 1000)),
            "device": self.settings["device_settings"]
        }
        
        if isinstance(image_path, list) and len(image_path) == 1:
            image_path = image_path[0]
        
        post_url = POST_URL_TEXTONLY
        if image_path is not None:
            if isinstance(image_path, str):
                post_url = POST_URL_IMAGE           
                upload_id = self._upload_image(image_path)
                if upload_id is not None:
                    params["upload_id"] = upload_id["upload_id"]
                    params["scene_capture_type"] = ""
            elif isinstance(image_path, list):
                post_url = POST_URL_SIDECAR
                params["client_sidecar_id"] = int(time.time() * 1000)
                params["children_metadata"] = []
                for image in image_path:
                    upload_id = self._upload_image(image)
                    if upload_id is None: continue
                    
                    params["children_metadata"] += [{
                        "upload_id": upload_id["upload_id"],
                        "source_type": "4",
                        "timezone_offset": str(self.settings["timezone_offset"]),
                        "scene_capture_type": "",
                    }]
        elif url is not None:
            params["text_post_app_info"]["link_attachment_url"] = url
            
        if image_path is None:
            params["publish_mode"] = "text_post"
            
        if parent_post_id is not None:
            params["text_post_app_info"]["reply_id"] = parent_post_id

        if quoted_post_id is not None:
            params["text_post_app_info"]["quoted_post_id"] = quoted_post_id
        
        params = json.dumps(params)
        payload = f"signed_body=SIGNATURE.{urllib.parse.quote(params)}"
        res = self.post_private_request(post_url, None, self.generate_headers(), payload)
        return res.json()["status"] == "ok", res.json()

def can_repost(id, max):
    conn = sqlite3.connect("C:/Threads/posts.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT repost_count FROM posts WHERE id = ?", (id,))
    result = cursor.fetchone()
    
    if result and result[0] > max:
        conn.close()
        return False
    
    if result:
        cursor.execute("UPDATE posts SET repost_count = repost_count + 1 WHERE id = ?", (id,))
    else:
        cursor.execute("INSERT INTO posts (id, repost_count) VALUES (?, 1)", (id,))
    
    conn.commit()
    conn.close()
    return True

def get_accounts() -> list[str]:
    conn = sqlite3.connect("C:/Threads/thread/accounts.db", check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute("SELECT account FROM accounts")
    result = cursor.fetchall()
    accounts_list = [row[0] for row in result]
    
    for i, account in enumerate(accounts_list):
        if "." in account.split(":")[-1]:
            last_dot_index = account.rfind('.')
            accounts_list[i] = account[:last_dot_index]
    
    conn.close()
    
    return accounts_list

def push_to_accounts(account):
    conn = sqlite3.connect("C:/Threads/thread/accounts.db", check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute("INSERT INTO accounts (account) VALUES (?)", (account,))
    conn.commit()
    
    conn.close()

def replace_account(from_account, to_account):
    conn = sqlite3.connect("C:/Threads/thread/accounts.db", check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute("UPDATE accounts SET account = ? WHERE account LIKE ?", (to_account, f"%{from_account}%"))
    conn.commit()
    
    conn.close()

def remove_account(account):
    conn = sqlite3.connect("C:/Threads/thread/accounts.db", check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM accounts WHERE account LIKE ?", (f"%{account}%",))
    conn.commit()
    
    conn.close()

def upload(username, password, email, email_password, proxy, thread_index: int, captions: list = [], images: str | list | None = None, comment_count: int = 20, search_query: str | None = None, spam_method: int = 0, captcha_key: str = "", cookies: str = "", serialized_settings: str = "", telegram_token: str = "", telegram_chat_id: str = "", original_spam_method: int = 0, max_time_seconds: int = 0, minimum_likes: int = 0, minimum_replies: int = 0, disable_comments: bool = False, avatar_folder: str = "", max_posts_on_post: int = 3, min_views_on_post: int = 500, post_links: list = [], set_image_on_rec: bool = True, set_image_on_warm: bool = True):
    last_exception = None

    if proxy is not None and "|" in proxy:
        link = proxy.split("|")[1]
        requests.get(link)
        proxy = proxy.split("|")[0]
    
    Logger.Log(f"[thread#{thread_index}] Started @{username}", Fore.GREEN)
    threads = Threads(proxy=proxy, key=captcha_key, thread_index=thread_index, serialized_settings=serialized_settings)
    if cookies == "":
        threads.login(username, password, email, email_password)
    else:
        iam = IAMParser.parse(cookies)
        if "uuid" in iam:
            threads.cl.set_uuids(iam["uuid"])
        if "user-agent" in iam:
            threads.cl.set_user_agent(iam["user-agent"])
        if "device" in iam:
            threads.cl.set_device(iam["device"])
        if "cookies" in iam:
            threads.global_extra_header = iam["cookies"]
            threads.token = iam["cookies"]["Authorization"].split("Bearer IGT:2:")[1]
    Logger.Log(f"[thread#{thread_index}] Loggined @{username}", Fore.GREEN)

    today = datetime.datetime.now()
    
    if not os.path.exists(f"C:/Threads/history/{today.month}.{today.day}"):
        os.makedirs(f"C:/Threads/history/{today.month}.{today.day}")
    
    relogged = False
    try:
        if len(threads.token) == 0:
            return "empty_token", 0
        
        Logger.Log(f"[thread#{thread_index}] Profile create status: " + threads.set_text_post_app_onboarding()["status"], Fore.GREEN)
    except LogoutException as e:
        last_exception = e
        with open(f"C:/Threads/history/{today.month}.{today.day}/failed.txt", "a") as f:
            f.write(f"{username}:{password}" + (f":{email}:{email_password}" if len(email) > 0 else "") + f" - 0" + (f" | {repr(last_exception)}" if last_exception is not None else "") + (f" | {threads.last_response.text}" if threads.last_response is not None else "") + "\n")
        Logger.Log(f"[thread#{thread_index}] Account logged out @{username}", Fore.RED)
        Logger.Log(f"[thread#{thread_index}] Finished upload @{username}", Fore.GREEN)
        return "logged_out", 0
    except AccountSuspendedException as e:
        last_exception = e
        with open(f"C:/Threads/history/{today.month}.{today.day}/failed.txt", "a") as f:
            f.write(f"{username}:{password}" + (f":{email}:{email_password}" if len(email) > 0 else "") + f" - 0" + (f" | {repr(last_exception)}" if last_exception is not None else "") + (f" | {threads.last_response.text}" if threads.last_response is not None else "") + "\n")
        Logger.Log(f"[thread#{thread_index}] Account suspended @{username}", Fore.RED)
        Logger.Log(f"[thread#{thread_index}] Finished upload @{username}", Fore.GREEN)
        return "account_suspended", 0
    except SubmitPhoneException as e:
        last_exception = e
        with open(f"C:/Threads/history/{today.month}.{today.day}/failed.txt", "a") as f:
            f.write(f"{username}:{password}" + (f":{email}:{email_password}" if len(email) > 0 else "") + f" - 0" + (f" | {repr(last_exception)}" if last_exception is not None else "") + (f" | {threads.last_response.text}" if threads.last_response is not None else "") + "\n")
        Logger.Log(f"[thread#{thread_index}] Submit phone @{username}", Fore.RED)
        Logger.Log(f"[thread#{thread_index}] Finished upload @{username}", Fore.GREEN)
        return "submit_phone", 0
    
    if len(avatar_folder.strip()) != 0 and os.path.exists(avatar_folder) and not threads.is_avatar_set():
        avatar_folder_list = os.listdir(avatar_folder)
        avatar = avatar_folder + "/" + random.choice(avatar_folder_list)
        
        res = threads._upload_image(avatar, True)
        Logger.Log(f"[thread#{thread_index}] Upload avatar file : {res['status']}", Fore.GREEN)
        if res["status"] == "ok":
            res = threads.post_private_request("https://i.instagram.com/api/v1/accounts/edit_profile/", None, threads.generate_headers(), {
                "external_url": "",
                "url_title": "",
                "biography": "",
                "_uuid": threads.cl.uuid,
                "is_private": "false",
                "upload_id": res["upload_id"]
            }).json()

            Logger.Log(f"[thread#{thread_index}] Edit profile : {res['status']}", Fore.GREEN)

    if spam_method == 4:
        successful_posts = 0
        # Logger.Log(f"[thread#{thread_index}] Warm 2.0", Fore.GREEN)
        
        while True:
            if successful_posts >= 5:
                break

            post = threads.get_post_by_url(random.choice(post_links))

            id = str(post["media"]["pk"])
            post_status = threads.post(caption=random.choice(captions), image_path=None if (not set_image_on_warm and spam_method == 4) else images, parent_post_id=id, disable_comments=disable_comments)[1]["status"]
            Logger.Log(f"[thread#{thread_index}] Warm 2.0 | Post status : {post_status} ({successful_posts+1}/{5})", Fore.GREEN)

            if post_status == "ok":
                successful_posts += 1 

        spam_method = 0

    max_id = None
    rank_token = None
    page_token = None
    posts_counts = 0
    successful_posts = 0
    relogged = False
    empty_pages = 0
    uploaded_id = []
    has_more = True
    while True:
        try:
            # if original_spam_method == 3 and random.randint(1, 5) == 1:
            #     spam_method = random.randint(0, 2)
            
            res = threads.get_timeline(max_id, empty_pages>=200) if spam_method == 0 else threads.fbsearch_text_app_serp(search_query, spam_method-1, rank_token, page_token, empty_pages>=200 or not has_more)
            max_id = res.get("next_max_id", None)
            rank_token = res.get("rank_token", None)
            page_token = res.get("page_token", None)
            
            if empty_pages >= 200 or not has_more: empty_pages = 0
            
            has_more = res.get("has_more", True)
            
            time.sleep(random.uniform(1, 3))
            
            if len(res.get("feed_items", [])) == 0 and len(res.get("threads", [])) == 0:
                max_id = None
                rank_token = None
                page_token = None
                empty_pages = 200
                continue

            Logger.Log(f"[thread#{thread_index}] Received {len(res.get('feed_items', [])) + len(res.get('threads', []))} posts", Fore.GREEN)
            
            for feed in res.get("feed_items", []) + res.get("threads", []):
                try:
                    if "text_post_app_thread" in feed:
                        post = feed["text_post_app_thread"]["thread_items"][0]["post"]
                    elif "thread_items" in feed:
                        post = feed["thread_items"][0]["post"]
                    else:
                        continue
                    
                    id = str(post["pk"])
                    taken_at = post["taken_at"]
                    like_count = post["like_count"]
                    direct_reply_count = post["text_post_app_info"]["direct_reply_count"]
                    
                    if time.time() - taken_at >= max_time_seconds or like_count < minimum_likes or direct_reply_count < minimum_replies or not can_repost(id, max_posts_on_post) or id in uploaded_id or threads.get_views(id) < min_views_on_post:
                        failed_text = []

                        if time.time() - taken_at >= max_time_seconds: failed_text.append("time")
                        if like_count < minimum_likes: failed_text.append("likes")
                        if direct_reply_count < minimum_replies: failed_text.append("comments")
                        if id in uploaded_id: failed_text.append("already posted")
                        if not can_repost(id, max_posts_on_post): failed_text.append("already posted")
                        if threads.get_views(id) < min_views_on_post: failed_text.append("views")

                        Logger.Log(f"[thread#{thread_index}] Requirements not match: {', '.join(failed_text)}", Fore.YELLOW)

                        empty_pages += 1
                        continue
                    
                    uploaded_id.append(id)
                    
                    post_status = threads.post(caption=random.choice(captions), image_path=None if (not set_image_on_rec and spam_method == 0) or (not set_image_on_warm and spam_method in [1, 2]) else images, parent_post_id=id, disable_comments=disable_comments)[1]["status"]
                    Logger.Log(f"[thread#{thread_index}] Post status : {post_status} ({successful_posts+1}/{comment_count})", Fore.GREEN)
                    
                    if post_status == "ok":
                        successful_posts += 1
                        relogged = False
                    
                    time.sleep(random.randint(60, 120))
                    
                    posts_counts += 1
                    if posts_counts >= comment_count: break
                except Exception as e: Logger.Log(f"[thread#{thread_index}] {repr(e)}", Fore.RED)
            if posts_counts >= comment_count: break
        except LogoutException as e:
            last_exception = e
            if relogged or cookies != "":
                Logger.Log(f"[thread#{thread_index}] Account logged out @{username}", Fore.RED)
                return "logged_out", successful_posts
            else:
                Logger.Log(f"[thread#{thread_index}] Trying relogin @{username}", Fore.YELLOW)
                relogged = True
                threads.login(username, password, email, email_password, True)
        except AccountSuspendedException as e:
            last_exception = e
            Logger.Log(f"[thread#{thread_index}] Account suspended @{username}", Fore.RED)
            return "account_suspended", successful_posts
        except SubmitPhoneException as e:
            last_exception = e
            Logger.Log(f"[thread#{thread_index}] Submit phone @{username}", Fore.RED)
            return "submit_phone", successful_posts
        except InfiniteSolveChallenge as e:
            last_exception = e
            Logger.Log(f"[thread#{thread_index}] Infinite solve challenge @{username}", Fore.RED)
            return "infinite_solve", successful_posts
        except Exception as e:
            last_exception = e
            Logger.Log(f"[thread#{thread_index}] {repr(e)}", Fore.RED)
    
    if posts_counts >= comment_count:
        with open(f"C:/Threads/history/{today.month}.{today.day}/successful_all.txt", "a") as f:
            f.write(f"{username}:{password}" + (f":{email}:{email_password}" if len(email) > 0 else "") + "\n")
        with open(f"C:/Threads/history/{today.month}.{today.day}/successful_warm.txt", "a") as f:
            f.write(f"{username}:{password}" + (f":{email}:{email_password}" if len(email) > 0 else "") + (f":{cookies}" if len(cookies) > 0 else "") + "\n")
    else:
        with open(f"C:/Threads/history/{today.month}.{today.day}/failed.txt", "a") as f:
            f.write(f"{username}:{password}" + (f":{email}:{email_password}" if len(email) > 0 else "") + f" - {successful_posts}" + (f" | {repr(last_exception)}" if last_exception is not None else "") + (f" | {threads.last_response.text}" if threads.last_response is not None else "") + "\n")
    
    Logger.Log(f"[thread#{thread_index}] Finished upload @{username}", Fore.GREEN)
    return "ok", successful_posts


def slice_list(lst, N):
    k, m = divmod(len(lst), N)
    return [lst[i*k + min(i, m):(i+1)*k + min(i+1, m)] for i in range(N)]

def upload_manager(serialized_settings: str, thread_index):
    settings = Settings(serialized_settings)
    
    asocks = None
    if len(settings.asocks_key.strip()) > 0:
        asocks = Asocks(settings.asocks_key)
    
    original_spam_method = settings.spam_method
    
    accounts = open(settings.accounts_file, "r", encoding="utf-8").readlines()
    
    proxies = open(settings.proxies_file, "r", encoding="utf-8").readlines()
    texts = open(settings.text_file, "r", encoding="utf-8").readlines()
    images = settings.images

    post_files = []
    if os.path.exists(settings.posts_file):
        post_files = open(settings.posts_file, "r", encoding="utf-8").readlines()
    
    search_queries = open(settings.search_query_file, "r", encoding="utf-8").readlines()
    
    if isinstance(accounts, str): accounts = [accounts]
    if isinstance(proxies, str): proxies = [proxies]
    
    if len(images) == 0:
        images = None
    elif len(images) == 1:
        images = images[0]
    
    if len(accounts) >= settings.threads:
        accounts = slice_list(accounts, settings.threads)[thread_index]
    if len(proxies) >= settings.threads:
        proxies = slice_list(proxies, settings.threads)[thread_index]
    
    accounts = [v.strip() for v in accounts]
    
    # existing_accounts = "\n".join(get_accounts())
    # for i, account in enumerate(accounts):
    #     if account.split(":")[0] not in existing_accounts:
    #         accounts[i] = account + ":1:1" if original_spam_method == 0 else ":0:0"
    #         push_to_accounts(accounts[i])
    
    # accounts = get_accounts()
    # accounts = slice_list(accounts, settings.threads)[thread_index]
    
    index = 0
    uploaded = 0
    posted = 0
    banned = 0
    with_error = 0
    while True:
        time.sleep(0.1)
            
        if index >= len(accounts) and settings.cirlce_upload:
            index = 0
        if index >= len(accounts) and not settings.cirlce_upload:
            break
        
        # try:
        #     if thread_index == 0 and os.path.exists("C:/Threads/thread/new_accounts.txt"):
        #         existing_accounts = "\n".join(get_accounts())
            
        #         new_accounts = open("C:/Threads/thread/new_accounts.txt", "r", encoding="utf-8").readlines()
        #         new_accounts = [v.strip() for v in new_accounts]
                    
        #         for i, new_account in enumerate(new_accounts):
        #             if new_account.split(":")[0] not in existing_accounts:
        #                 new_accounts[i] = new_account + (":1:1" if original_spam_method == 0 else ":0:0")
        #                 push_to_accounts(new_accounts[i])
                        
        #         os.remove("C:/Threads/thread/new_accounts.txt")
                
        #         accounts = get_accounts()
        #         accounts = slice_list(accounts, settings.threads)[thread_index]
        # except Exception as e:
        #     Logger.Log(f"Failed to load new accounts {repr(e)}", Fore.RED)
        
        try:
            account = accounts[index]
        except IndexError:
            index = 0
            continue
        
        # if len(account.strip()) == 0 or int(account.split(":")[-1]) > time.time(): 
        #     index += 1
        #     accounts = get_accounts()
        #     accounts = slice_list(accounts, settings.threads)[thread_index]
        #     continue
        
        # account_state = int(account.split(":")[-2])
        
        # if account_state == 0:
        #     settings.comments = 5
        #     settings.spam_method = 1
        #     account_state = 1
        # elif account_state == 1:
        #     settings.comments = settings.comments
        #     settings.spam_method = 0
        #     account_state = 1

        settings.spam_method = original_spam_method
        if settings.spam_method == 3:
            settings.spam_method = random.randint(1, 3)

        if settings.spam_method == 3: settings.spam_method = 4
        
        state = "exception"
        
        if asocks is not None:
            proxy, id = asocks.create_port(settings.country_code, settings.state, settings.city, int(settings.asn), 1, 2, None, 1, 1)
            proxies = [proxy]
        
        post_count = 0
        try:
            if "Bearer IGT:2:" not in account:
                state, post_count = upload(account.split(":")[0].strip(), account.split(":")[1].strip(), account.split(":")[2].strip(), account.split(":")[3].strip(), proxies[index % len(proxies)] if len(proxies) > 0 else None, thread_index, texts, images, settings.comments, random.choice(search_queries).strip() if len(search_queries) > 0 else None, settings.spam_method, settings.captcha_key, serialized_settings=serialized_settings, telegram_token=settings.telegram_token, telegram_chat_id=settings.telegram_chat_id, original_spam_method=settings.spam_method, max_time_seconds=settings.max_time_seconds, minimum_likes=settings.minimum_likes, minimum_replies=settings.minimum_replies, disable_comments=settings.disable_comments, avatar_folder=settings.avatar_folder, max_posts_on_post=settings.max_posts_on_post, min_views_on_post=settings.min_views_on_post, post_links=post_files, set_image_on_rec=settings.set_image_on_rec, set_image_on_warm=settings.set_image_on_warm)
            else:
                state, post_count = upload(account.split(":")[0].strip(), account.split(":")[1].split("|")[0].strip(), "", "", proxies[index % len(proxies)] if len(proxies) > 0 else None, thread_index, texts, images, settings.comments, random.choice(search_queries).strip() if len(search_queries) > 0 else None, settings.spam_method, settings.captcha_key, account, serialized_settings=serialized_settings, telegram_token=settings.telegram_token, telegram_chat_id=settings.telegram_chat_id, original_spam_method=settings.spam_method, max_time_seconds=settings.max_time_seconds, minimum_likes=settings.minimum_likes, minimum_replies=settings.minimum_replies, disable_comments=settings.disable_comments, avatar_folder=settings.avatar_folder, max_posts_on_post=settings.max_posts_on_post, min_views_on_post=settings.min_views_on_post, post_links=post_files, set_image_on_rec=settings.set_image_on_rec, set_image_on_warm=settings.set_image_on_warm)
        except Exception as e: 
            Logger.LogFile(f"[#thread{thread_index}] {traceback.format_exc()}")
            Logger.Log(f"[#thread{thread_index}] {repr(e)}", Fore.RED)
        
        posted += post_count

        if asocks is not None:
            asocks.delete_port(id)
        
        next_time = time.time()
            
        if state == "ok": 
            # next_time += 3600*6
            uploaded += 1
        if state == "infinite_solve": 
            # next_time += 3600*6
            with_error += 1
        if state == "submit_phone": 
            # next_time += 3600*24*3
            with_error += 1
        if state == "logged_out": 
            # next_time += 0
            with_error += 1
        if state == "empty_token": 
            # next_time += time.time() # newer :\
            banned += 1
            # remove_account(account)
        if state == "account_suspended": 
            # next_time += time.time() # newer :\
            banned += 1
            # remove_account(account)
        
        # next_time = int(next_time)
        
        if state == "empty_token" or state == "account_suspended":
            with multiprocessing.Lock():
                with open(settings.accounts_file, "r") as f:
                    acc = f.readlines()

                acc = [v.strip() for v in acc]
                acc = [v for v in acc if account not in v]

                with open(settings.accounts_file, "w") as file:
                    file.write("\n".join(acc) + "\n")  

        if settings.telegram_token != "" and settings.telegram_chat_id:
            bot = telebot.TeleBot(token=settings.telegram_token, threaded=False)
            bot.send_message(settings.telegram_chat_id, f"Аккаунт пролит <code>@{account.split(':')[0].strip()}</code>: {state}", parse_mode="html")
        
        # replace_account(account, re.sub(r"(:\d+)+$", "", account) + f":{account_state}:{next_time}")
        
        # accounts = get_accounts()
        # accounts = slice_list(accounts, settings.threads)[thread_index]
        
        index += 1


    if settings.telegram_token != "" and settings.telegram_chat_id:
        bot = telebot.TeleBot(token=settings.telegram_token, threaded=False)
        bot.send_message(settings.telegram_chat_id, f"<b>Статистика потока:</b>\nАккаунтов залито: {uploaded}\nПостов залито: {posted}\nЗабаненно: {banned}\nС ошибкой: {with_error}", parse_mode="html")