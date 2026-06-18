import flet as ft
import os
from tkinter import filedialog
from multiprocessing import Process
from upload import upload_manager, Asocks
from settings import Settings
import sqlite3
import asyncio
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram import Bot, Dispatcher, types, F
import colorama

class FileSelector(ft.Row):
    
    def __init__(self, label, value, font_family, font_size, font_weight, on_change, visible = True, dialog_title: str = "", is_dir: bool = False):
        super().__init__()
        
        self.label = label
        self.value = value
        self.on_change = on_change
        self.dialog_title = dialog_title
        self.is_dir = is_dir
        self.visible = visible
        self.controls=[
            ft.Text(self.format_str(label), font_family=font_family, size=font_size, weight=font_weight),
            ft.Row(controls=[
                ft.TextButton(content=ft.Container(ft.Icon(ft.icons.FOLDER, color=ft.colors.RED_ACCENT_400)), on_click=lambda e: self._select_btn()),
                ft.TextButton(content=ft.Container(ft.Icon(ft.icons.DELETE, color=ft.colors.RED_ACCENT_400)), on_click=lambda e: self._delete()),
            ])
        ]
        self.alignment = ft.MainAxisAlignment.SPACE_BETWEEN

    def format_str(self, text):
        if self.is_dir:
            if os.path.exists(self.value): return text.replace("{count}", str(len(os.listdir(self.value))))
            else: return text.replace("{count}", "0")
        return text.replace("{count}", str(len(self.value)))

    def _delete(self):
        self.value = "" if self.is_dir else []
        self.controls[0].value = self.format_str(self.label)
        self.update()
        self.on_change(self.value)
        
    def _select_btn(self):
        if self.is_dir:
            new_selected = filedialog.askdirectory(title=self.dialog_title, mustexist=True)
            if len(new_selected) > 0:
                self.value = new_selected
                image_files = [file for file in os.listdir(self.value) if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.mp4', '.mov', '.avi', '.webm', '.mp3'))]
                self.controls[0].value = self.format_str(self.label)
                self.update()
                if self.on_change is not None:
                    self.on_change(self.value)
        else:
            new_selected = filedialog.askopenfilenames(title=self.dialog_title)
            if len(new_selected) > 0:
                self.value = new_selected
                self.controls[0].value = self.format_str(self.label)
                self.update()
                if self.on_change is not None:
                    self.on_change(self.value)

class UploadApp:
    
    instance = None
    
    def __init__(self, page: ft.Page):        
        self.page = page
        
        UploadApp.instance = self
        
        self.page.on_route_change = self.on_route_change
        
        self.page.title = "Upload Manager"
        self.threads_list = []
        
        self.page.window.minimizable = False
        self.page.window.resizable = False
        self.page.window.width = 500
        self.page.window.height = 870
        
        self.page.theme = ft.Theme(
            color_scheme_seed=ft.colors.RED
        )

        self.page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        self.page.vertical_alignment = ft.MainAxisAlignment.CENTER

        self.accounts_btn = ft.ElevatedButton("Выбрать аккаунты", on_click=self.select_accounts, color=ft.colors.WHITE, bgcolor=ft.colors.RED_600)
        self.proxy_btn = ft.ElevatedButton("Выбрать прокси", on_click=self.select_proxy, color=ft.colors.WHITE, bgcolor=ft.colors.RED_600)
        self.images_btn = ft.ElevatedButton("Выбрать картинки", on_click=self.select_images, color=ft.colors.WHITE, bgcolor=ft.colors.RED_600)
        self.text_btn = ft.ElevatedButton("Выбрать текст для поста", on_click=self.select_text, color=ft.colors.WHITE, bgcolor=ft.colors.RED_600)
        self.post_link_btn = ft.ElevatedButton("Выбрать ссылки на пост", on_click=self.select_post_link, visible=Settings.get_instance().spam_method in [3, 4], color=ft.colors.WHITE, bgcolor=ft.colors.RED_600)
        self.search_query_btn = ft.ElevatedButton("Выбрать текст для поиска", on_click=self.select_search_query, visible=Settings.get_instance().spam_method in [1, 2, 3], color=ft.colors.WHITE, bgcolor=ft.colors.RED_600)
        self.spam_method = ft.CupertinoSlidingSegmentedButton([ft.Text("Рекомендации"), ft.Text("Поиск 'Топ'"), ft.Text("Поиск 'Недавнее'"), ft.Text("Случайное"), ft.Text("Прогрев2.0+реки")], selected_index=Settings.get_instance().spam_method, on_change=self.spam_method_change, thumb_color=ft.colors.RED_600)
        self.unique_photo = ft.CupertinoSlidingSegmentedButton([ft.Text("Уникализировать"), ft.Text("Не уникализировать")], selected_index=Settings.get_instance().unique_photo, on_change=self.unique_photo_change, thumb_color=ft.colors.RED_600)
        self.unique_photo_btn = ft.ElevatedButton("Настройки уникализатора", on_click=self.unique_photo_btn_click, visible=Settings.get_instance().unique_photo==0, color=ft.colors.WHITE, bgcolor=ft.colors.RED_600)
        
        self.max_time_seconds_btn = ft.TextField(label="Максимальное время поста (сек)", width=480, value=Settings.get_instance().max_time_seconds, on_change=self.max_time_seconds_update)
        self.minimum_likes_btn = ft.TextField(label="Минимальное количество лайков", width=480, value=Settings.get_instance().minimum_likes, on_change=self.minimum_likes_update)
        self.minimum_replies_btn = ft.TextField(label="Минимальное количество комментариев", width=480, value=Settings.get_instance().minimum_replies, on_change=self.minimum_replies_update)
        self.min_views_on_post_btn = ft.TextField(label="Минимальное количество просмотров", width=480, value=Settings.get_instance().min_views_on_post, on_change=self.min_views_on_post_update)
        self.max_posts_on_post_btn = ft.TextField(label="Сколько комментариев софт сможет залить на 1 пост", width=480, value=Settings.get_instance().max_posts_on_post, on_change=self.max_posts_on_post_update)

        self.disable_comments_btn = ft.Checkbox("Отключить комментарии на посте?", value=Settings().get_instance().disable_comments, on_change=self.disable_comments_update)
        self.cirlce_upload_btn = ft.Checkbox("Лить кругами?", value=Settings().get_instance().cirlce_upload, on_change=self.cirlce_upload_update)
        self.set_image_on_rec_btn = ft.Checkbox("Постить картинку? (Реки)", value=Settings().get_instance().set_image_on_rec, on_change=self.set_image_on_rec_update)
        self.set_image_on_warm_btn = ft.Checkbox("Постить картинку? (Прогрев)", value=Settings().get_instance().set_image_on_warm, on_change=self.set_image_on_warm_update)

        self.captcha_key = ft.TextField(label="AntiCaptcha API key", value=Settings.get_instance().captcha_key, on_change=self.update_captcha_key)
        self.asocks_key = ft.TextField(label="Asocks API key", width=400 if len(Settings.get_instance().asocks_key.strip()) > 0 else 480, value=Settings.get_instance().asocks_key, on_change=self.update_asocks_key)
        self.asocks_settings = ft.IconButton(ft.icons.SETTINGS, visible=len(Settings.get_instance().asocks_key.strip()) > 0, icon_color=ft.colors.RED, on_click=self.asocks_settings_btn)
        self.telegram_token = ft.TextField(label="Telegram Bot Token", value=Settings.get_instance().telegram_token, on_change=self.telegram_token_change)
        self.telegram_chat_id = ft.TextField(label="Telegram Chat ID", value=Settings.get_instance().telegram_chat_id, on_change=self.telegram_chat_id_change)

        self.threads_label = ft.Text(f"Количество потоков ({Settings.get_instance().threads}):", color=ft.colors.RED)
        self.threads_slider = ft.Slider(
            min=1, max=100 if Settings.get_instance().threads >= 30 else 30, value=Settings.get_instance().threads, round=0, width=300, on_change=self.update_threads_text, active_color=ft.colors.RED_700, thumb_color=ft.colors.RED_ACCENT_200
        )
        
        self.comment_label = ft.Text(f"Количество комментов ({Settings.get_instance().comments}):", color=ft.colors.RED)
        self.comment_slider = ft.Slider(
            min=1, max=50, value=Settings.get_instance().comments, round=0, width=300, on_change=self.update_comment_text, active_color=ft.colors.RED_700, thumb_color=ft.colors.RED_ACCENT_200
        )
        
        self.start_upload_btn = ft.ElevatedButton("Начать залив", on_click=self.start_upload, color=ft.colors.WHITE, bgcolor=ft.colors.RED_600)

        self.unique_container = ft.Container(content=ft.Column(controls=[], horizontal_alignment=ft.CrossAxisAlignment.START, width=450, height=750, scroll=True))
        self.asocks_container = ft.Container(content=ft.Column(controls=[], horizontal_alignment=ft.CrossAxisAlignment.START, width=450, height=750, scroll=True))

        self.page.add(*self.get_base_page())
    
    def avatar_folder_update(self, e):
        Settings.get_instance().avatar_folder = e
        Settings.get_instance().save()
    
    def disable_comments_update(self, e):
        Settings.get_instance().disable_comments = e.control.value
        Settings.get_instance().save()
    
    def cirlce_upload_update(self, e):
        Settings.get_instance().cirlce_upload = e.control.value
        Settings.get_instance().save()
    
    def set_image_on_rec_update(self, e):
        Settings.get_instance().set_image_on_rec = e.control.value
        Settings.get_instance().save()
    
    def set_image_on_warm_update(self, e):
        Settings.get_instance().set_image_on_warm = e.control.value
        Settings.get_instance().save()

    def max_posts_on_post_update(self, e):
        try:
            Settings.get_instance().max_posts_on_post = int(e.control.value)
            Settings.get_instance().save()
        except Exception: pass

    def max_time_seconds_update(self, e):
        try:
            Settings.get_instance().max_time_seconds = int(e.control.value)
            Settings.get_instance().save()
        except Exception: pass
    
    def minimum_likes_update(self, e):
        try:
            Settings.get_instance().minimum_likes = int(e.control.value)
            Settings.get_instance().save()
        except Exception: pass
    
    def minimum_replies_update(self, e):
        try:
            Settings.get_instance().minimum_replies = int(e.control.value)
            Settings.get_instance().save()
        except Exception: pass
    
    def min_views_on_post_update(self, e):
        try:
            Settings.get_instance().min_views_on_post = int(e.control.value)
            Settings.get_instance().save()
        except Exception: pass

    def asocks_settings_btn(self, e):
        self.page.route = "asocks"
        self.page.update()
    
    def telegram_token_change(self, e):
        Settings.get_instance().telegram_token = e.control.value
        Settings.get_instance().save()

    def telegram_chat_id_change(self, e):
        Settings.get_instance().telegram_chat_id = e.control.value
        Settings.get_instance().save()
        
    def asocks_page(self):
        asocks = Asocks(Settings.get_instance().asocks_key)
        
        countries_list = asocks.dir_countries()
        selected_country_id = [v["id"] for v in countries_list if v["code"] == Settings.get_instance().country_code][0] if len([v["id"] for v in countries_list if v["code"] == Settings.get_instance().country_code]) > 0 else -1
        
        state_list = asocks.dir_states(selected_country_id)
        selected_state_id = [v["id"] for v in state_list if v["name"] == Settings.get_instance().state][0] if len([v["id"] for v in state_list if v["name"] == Settings.get_instance().state]) > 0 else -1
        
        cities_list = asocks.dir_cities(selected_country_id, selected_state_id)
        selected_city_id = [v["id"] for v in cities_list if v["name"] == Settings.get_instance().city][0] if len([v["id"] for v in cities_list if v["name"] == Settings.get_instance().city]) > 0 else -1
        
        asns_list = asocks.dir_asns(selected_country_id, selected_state_id, selected_city_id)
        
        def set_country(e):
            nonlocal state_list, countries_list, cities_list, asns_list
            
            Settings.get_instance().country_code = e.control.value
            Settings.get_instance().save()
            state_list = asocks.dir_states([v["id"] for v in countries_list if v["code"] == Settings.get_instance().country_code][0])
            
            self.asocks_container.content.controls = generate_page()
            self.asocks_container.content.update()
            
        def set_state(e):
            nonlocal state_list, countries_list, cities_list, asns_list
            
            Settings.get_instance().state = e.control.value
            Settings.get_instance().save()
            cities_list = asocks.dir_cities([v["id"] for v in countries_list if v["code"] == Settings.get_instance().country_code][0], [v["id"] for v in state_list if v["name"] == Settings.get_instance().state][0])
            
            self.asocks_container.content.controls = generate_page()
            self.asocks_container.content.update()
            
        def set_city(e):
            nonlocal state_list, countries_list, cities_list, asns_list
            
            Settings.get_instance().city = e.control.value
            Settings.get_instance().save()
            asns_list = asocks.dir_asns([v["id"] for v in countries_list if v["code"] == Settings.get_instance().country_code][0], [v["id"] for v in state_list if v["name"] == Settings.get_instance().state][0], [v["id"] for v in cities_list if v["name"] == Settings.get_instance().city][0])
            
            self.asocks_container.content.controls = generate_page()
            self.asocks_container.content.update()
        
        def set_asn(e):
            nonlocal state_list, countries_list, cities_list, asns_list
            
            Settings.get_instance().asn = e.control.value
            Settings.get_instance().save()
        
        def generate_page():
            return [
                ft.IconButton(ft.icons.ARROW_BACK, icon_color=ft.colors.RED_ACCENT_400, on_click=self.unique_back_btn_click),
                ft.Dropdown(value=Settings.get_instance().country_code, on_change=set_country, options=[ft.dropdown.Option(v["code"], v["name"]) for v in countries_list]),
                ft.Dropdown(value=Settings.get_instance().state, on_change=set_state, options=[ft.dropdown.Option(v["name"]) for v in state_list]),
                ft.Dropdown(value=Settings.get_instance().city, on_change=set_city, options=[ft.dropdown.Option(v["name"]) for v in cities_list]),
                ft.Dropdown(value=Settings.get_instance().asn, on_change=set_asn, options=[ft.dropdown.Option(v["asn"]) for v in asns_list])
            ]
            
        self.asocks_container.content.controls = generate_page()
        
        return [self.asocks_container]
    
    def on_route_change(self, e):
        if self.page.route == "unique":
            self.page.controls = self.unique_page()
        elif self.page.route == "asocks":
            self.page.controls = self.asocks_page()
        else:
            self.page.controls = self.get_base_page()
        self.page.update()
    
    def unique_page(self):        
        def edit(name, value, element = None, text = ""):
            if name == "rotate_angle":
                Settings.get_instance().rotate_angle_min = value.start_value
                Settings.get_instance().rotate_angle_max = value.end_value
            elif name == "snow_size":
                Settings.get_instance().snow_size_min = value.start_value
                Settings.get_instance().snow_size_max = value.end_value
            else:
                Settings.get_instance().edit(name, value)
            self.unique_container.content.controls = generate_page_content()
            self.unique_container.content.update()

        def generate_page_content():
            return [
                ft.IconButton(ft.icons.ARROW_BACK, icon_color=ft.colors.RED_ACCENT_400, on_click=self.unique_back_btn_click),
                ft.Checkbox("Ставить фон", on_change=lambda e: edit("apply_bg", e.control.value), value=Settings.get_instance().apply_bg, label_style=ft.TextStyle(font_family="Heebo", weight=ft.FontWeight.W_500, size=14), fill_color={ft.ControlState.SELECTED: ft.colors.RED_ACCENT_400}, shape=ft.RoundedRectangleBorder(5)),
                FileSelector("Папка со своими фонами\nЗагружено фото - {count}", Settings.get_instance().bg_images_folder, "Heebo", 14, ft.FontWeight.W_500, lambda e: edit("bg_images_folder", e), visible=Settings.get_instance().apply_bg, is_dir=True, dialog_title="Select folder"),
                ft.Text("Размер фона - %.2f" % Settings.get_instance().background_scale, visible=Settings.get_instance().apply_bg, font_family="Heebo", weight=ft.FontWeight.W_500, size=14),
                ft.Slider(min=0, max=2, round=2, visible=Settings.get_instance().apply_bg, value=Settings.get_instance().background_scale, active_color=ft.colors.RED_ACCENT_400, on_change_end=lambda e: edit("background_scale", e.control.value)),
                ft.Checkbox("Генерировать фон (ИИ)", on_change=lambda e: edit("ai_generation", e.control.value), visible=Settings.get_instance().apply_bg, value=Settings.get_instance().ai_generation, label_style=ft.TextStyle(font_family="Heebo", weight=ft.FontWeight.W_500, size=14), fill_color={ft.ControlState.SELECTED: ft.colors.RED_ACCENT_400}, shape=ft.RoundedRectangleBorder(5)),
                ft.TextField(value=Settings.get_instance().prompt, visible=Settings.get_instance().apply_bg and Settings.get_instance().ai_generation, hint_text="Prompt", on_change=lambda e: Settings.get_instance().edit("prompt", e.control.value), border_color="#e9e9e9", focused_border_color=ft.colors.RED_ACCENT_400, width=400, border_radius=ft.border_radius.all(15)),
                ft.TextField(value=Settings.get_instance().negative_prompt, visible=Settings.get_instance().apply_bg and Settings.get_instance().ai_generation, hint_text="Negative prompt", on_change=lambda e: Settings.get_instance().edit("negative_prompt", e.control.value), border_color="#e9e9e9", focused_border_color=ft.colors.RED_ACCENT_400, width=400, border_radius=ft.border_radius.all(15)),
                ft.Checkbox("Генерировать фон", on_change=lambda e: edit("generate_background", e.control.value), visible=Settings.get_instance().apply_bg, value=Settings.get_instance().generate_background, label_style=ft.TextStyle(font_family="Heebo", weight=ft.FontWeight.W_500, size=14), fill_color={ft.ControlState.SELECTED: ft.colors.RED_ACCENT_400}, shape=ft.RoundedRectangleBorder(5)),
                ft.Checkbox("Рандомное положение", on_change=lambda e: edit("random_position", e.control.value), visible=Settings.get_instance().apply_bg, value=Settings.get_instance().random_position, label_style=ft.TextStyle(font_family="Heebo", weight=ft.FontWeight.W_500, size=14), fill_color={ft.ControlState.SELECTED: ft.colors.RED_ACCENT_400}, shape=ft.RoundedRectangleBorder(5)),
                ft.Checkbox("Добавить снег", on_change=lambda e: edit("snow", e.control.value), value=Settings.get_instance().snow, label_style=ft.TextStyle(font_family="Heebo", weight=ft.FontWeight.W_500, size=14), fill_color={ft.ControlState.SELECTED: ft.colors.RED_ACCENT_400}, shape=ft.RoundedRectangleBorder(5)),
                ft.Text("Количество снега - %.0f" % Settings.get_instance().snow_count, visible=Settings.get_instance().snow, font_family="Heebo", weight=ft.FontWeight.W_500, size=14),
                ft.Slider(min=1, max=500, round=0, visible=Settings.get_instance().snow, value=Settings.get_instance().snow_count, active_color=ft.colors.RED_ACCENT_400, on_change_end=lambda e: edit("snow_count", int(e.control.value))),
                ft.Text("Размер снега - [%.0f; %.0f]" % (Settings.get_instance().snow_size_min, Settings.get_instance().snow_size_max), visible=Settings.get_instance().snow, font_family="Heebo", weight=ft.FontWeight.W_500, size=14),
                ft.RangeSlider(min=1, max=100, round=0, visible=Settings.get_instance().snow, start_value=Settings.get_instance().snow_size_min, end_value=Settings.get_instance().snow_size_max, active_color=ft.colors.RED_ACCENT_400, on_change_end=lambda e: edit("snow_size", e.control)),
                FileSelector("Папка с текстурами для снега\nЗагружено фото - {count}", Settings.get_instance().snow_dir, "Heebo", 14, ft.FontWeight.W_500, lambda e: edit("snow_dir", e), visible=Settings.get_instance().snow, is_dir=True, dialog_title="Select folder"),
                ft.Checkbox("Добавить шум", on_change=lambda e: edit("noise_enabled", e.control.value), value=Settings.get_instance().noise_enabled, label_style=ft.TextStyle(font_family="Heebo", weight=ft.FontWeight.W_500, size=14), fill_color={ft.ControlState.SELECTED: ft.colors.RED_ACCENT_400}, shape=ft.RoundedRectangleBorder(5)),
                ft.Text("Интенсивность шума - %.2f" % Settings.get_instance().noise_intensity, visible=Settings.get_instance().noise_enabled, font_family="Heebo", weight=ft.FontWeight.W_500, size=14),
                ft.Slider(min=0, max=1, round=2, visible=Settings.get_instance().noise_enabled, value=Settings.get_instance().noise_intensity, active_color=ft.colors.RED_ACCENT_400, on_change_end=lambda e: edit("noise_intensity", e.control.value)),
                ft.Checkbox("Шум для фона", visible=Settings.get_instance().noise_enabled, on_change=lambda e: edit("noise_all", e.control.value), value=Settings.get_instance().noise_all, label_style=ft.TextStyle(font_family="Heebo", weight=ft.FontWeight.W_500, size=14), fill_color={ft.ControlState.SELECTED: ft.colors.RED_ACCENT_400}, shape=ft.RoundedRectangleBorder(5)),
                ft.Checkbox("Добавить линии", on_change=lambda e: edit("draw_lines", e.control.value), value=Settings.get_instance().draw_lines, label_style=ft.TextStyle(font_family="Heebo", weight=ft.FontWeight.W_500, size=14), fill_color={ft.ControlState.SELECTED: ft.colors.RED_ACCENT_400}, shape=ft.RoundedRectangleBorder(5)),
                ft.Text("Толщина линий - %.0f" % Settings.get_instance().line_thickness, visible=Settings.get_instance().draw_lines, font_family="Heebo", weight=ft.FontWeight.W_500, size=14),
                ft.Slider(min=0, max=10, round=0, visible=Settings.get_instance().draw_lines, value=Settings.get_instance().line_thickness, active_color=ft.colors.RED_ACCENT_400, on_change_end=lambda e: edit("line_thickness", e.control.value)),
                ft.Text("Размер линий - %.0f" % Settings.get_instance().line_width, visible=Settings.get_instance().draw_lines, font_family="Heebo", weight=ft.FontWeight.W_500, size=14),
                ft.Slider(min=0, max=20, round=0, visible=Settings.get_instance().draw_lines, value=Settings.get_instance().line_width, active_color=ft.colors.RED_ACCENT_400, on_change_end=lambda e: edit("line_width", e.control.value)),
                ft.Checkbox("Добавить эмодзи", on_change=lambda e: edit("emoji", e.control.value), value=Settings.get_instance().emoji, label_style=ft.TextStyle(font_family="Heebo", weight=ft.FontWeight.W_500, size=14), fill_color={ft.ControlState.SELECTED: ft.colors.RED_ACCENT_400}, shape=ft.RoundedRectangleBorder(5)),
                ft.Text("Количество эмодзи - %.0f" % Settings.get_instance().emoji_count, visible=Settings.get_instance().emoji, font_family="Heebo", weight=ft.FontWeight.W_500, size=14),
                ft.Slider(min=1, max=100, round=0, visible=Settings.get_instance().emoji, value=Settings.get_instance().emoji_count, active_color=ft.colors.RED_ACCENT_400, on_change_end=lambda e: edit("emoji_count", e.control.value)),
                ft.Text("Масштаб эмодзи - %.1f" % Settings.get_instance().emoji_scale_factor, visible=Settings.get_instance().emoji, font_family="Heebo", weight=ft.FontWeight.W_500, size=14),
                ft.Slider(min=0, max=10, round=1, visible=Settings.get_instance().emoji, value=Settings.get_instance().emoji_scale_factor, active_color=ft.colors.RED_ACCENT_400, on_change_end=lambda e: edit("emoji_scale_factor", e.control.value)),
                ft.Text("Непрозрачность эмодзи - %.2f" % Settings.get_instance().emoji_opacity, visible=Settings.get_instance().emoji, font_family="Heebo", weight=ft.FontWeight.W_500, size=14),
                ft.Slider(min=0, max=1, round=2, visible=Settings.get_instance().emoji, value=Settings.get_instance().emoji_opacity, active_color=ft.colors.RED_ACCENT_400, on_change_end=lambda e: edit("emoji_opacity", e.control.value)),
                ft.Checkbox("Отзеркалить по X", on_change=lambda e: edit("mirror_x", e.control.value), value=Settings.get_instance().mirror_x, label_style=ft.TextStyle(font_family="Heebo", weight=ft.FontWeight.W_500, size=14), fill_color={ft.ControlState.SELECTED: ft.colors.RED_ACCENT_400}, shape=ft.RoundedRectangleBorder(5)),
                ft.Checkbox("Отзеркалить по Y", on_change=lambda e: edit("mirror_y", e.control.value), value=Settings.get_instance().mirror_y, label_style=ft.TextStyle(font_family="Heebo", weight=ft.FontWeight.W_500, size=14), fill_color={ft.ControlState.SELECTED: ft.colors.RED_ACCENT_400}, shape=ft.RoundedRectangleBorder(5)),
                ft.Checkbox("Коррекция цвета", on_change=lambda e: edit("color_correction", e.control.value), value=Settings.get_instance().color_correction, label_style=ft.TextStyle(font_family="Heebo", weight=ft.FontWeight.W_500, size=14), fill_color={ft.ControlState.SELECTED: ft.colors.RED_ACCENT_400}, shape=ft.RoundedRectangleBorder(5)),
                ft.Checkbox("Случайный размер", on_change=lambda e: edit("random_size", e.control.value), value=Settings.get_instance().random_size, label_style=ft.TextStyle(font_family="Heebo", weight=ft.FontWeight.W_500, size=14), fill_color={ft.ControlState.SELECTED: ft.colors.RED_ACCENT_400}, shape=ft.RoundedRectangleBorder(5)),
                ft.Text("Непрозрачность изображения - %.2f" % Settings.get_instance().image_opacity, font_family="Heebo", weight=ft.FontWeight.W_500, size=14),
                ft.Slider(min=0, max=1, round=2, value=Settings.get_instance().image_opacity, active_color=ft.colors.RED_ACCENT_400, on_change_end=lambda e: edit("image_opacity", e.control.value)),
                ft.Text("Поворот изображения - [%.0f; %.0f]" % (Settings.get_instance().rotate_angle_min, Settings.get_instance().rotate_angle_max), font_family="Heebo", weight=ft.FontWeight.W_500, size=14),
                ft.RangeSlider(min=-90, max=90, round=0, start_value=Settings.get_instance().rotate_angle_min, end_value=Settings.get_instance().rotate_angle_max, active_color=ft.colors.RED_ACCENT_400, on_change_end=lambda e: edit("rotate_angle", e.control)),
                ft.Text(f"Качество изображения - {Settings.get_instance().quality}%", font_family="Heebo", weight=ft.FontWeight.W_500, size=14),
                ft.Slider(min=0, max=100, round=0, value=Settings.get_instance().quality, active_color=ft.colors.RED_ACCENT_400, on_change_end=lambda e: edit("quality", int(e.control.value))),
                ft.Text(f"Итоговый размер файла - {Settings.get_instance().final_image_size}%", font_family="Heebo", weight=ft.FontWeight.W_500, size=14),
                ft.Slider(min=0, max=100, round=0, value=Settings.get_instance().final_image_size, active_color=ft.colors.RED_ACCENT_400, on_change_end=lambda e: edit("final_image_size", int(e.control.value))),
                ft.Container(height=20),
                # ft.Container(ft.TextButton(content=ft.Text("Предпросмотр", weight=ft.FontWeight.W_700, size=14, font_family="Heebo", color=ft.colors.RED_ACCENT_400), on_click=lambda e: unique_module.preview_unique_photo(Settings.get_instance().images, Settings.get_instance()), style=ft.ButtonStyle(side=ft.BorderSide(1, ft.colors.RED_ACCENT_400))), width=450, alignment=ft.alignment.center),
                ft.Container(height=50)
            ]
            
        self.unique_container.content.controls = generate_page_content()
            
        return [self.unique_container]
    
    def get_base_page(self):
        return [
            ft.Column([
                self.accounts_btn,
                self.proxy_btn,
                self.images_btn,
                self.text_btn,
                self.spam_method,
                self.post_link_btn,
                self.search_query_btn,
                self.unique_photo,
                self.unique_photo_btn,
                self.threads_label,
                self.threads_slider,
                self.comment_label,
                self.comment_slider,
                self.captcha_key,
                ft.Row([
                    self.asocks_key,
                    self.asocks_settings
                ]),
                self.telegram_token,
                self.telegram_chat_id,
                self.disable_comments_btn,
                self.cirlce_upload_btn,
                self.set_image_on_rec_btn,
                self.set_image_on_warm_btn,
                FileSelector("Папка с аватарками\nЗагружено фото - {count}", Settings.get_instance().avatar_folder, "Heebo", 14, ft.FontWeight.W_500, lambda e: self.avatar_folder_update(e), is_dir=True, dialog_title="Select folder"),
                ft.Text("Настройка куда лить"),
                self.max_time_seconds_btn,
                self.minimum_likes_btn,
                self.minimum_replies_btn,
                self.min_views_on_post_btn,
                self.max_posts_on_post_btn,
                self.start_upload_btn,
                ft.Container(height=100)
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, height=870, scroll=ft.ScrollMode.ALWAYS)
        ]

    def unique_photo_btn_click(self, e):
        self.page.route = "unique"
        self.page.update()

    def unique_back_btn_click(self, e):
        self.page.route = "main"
        self.page.update()
        
    def spam_method_change(self, e):
        Settings.get_instance().spam_method = e.control.selected_index
        Settings.get_instance().save()
        self.search_query_btn.visible = e.control.selected_index in [1, 2, 3]
        self.post_link_btn.visible = e.control.selected_index in [3, 4]
        self.search_query_btn.update()
        self.post_link_btn.update()
        
    def unique_photo_change(self, e):
        Settings.get_instance().unique_photo = e.control.selected_index
        Settings.get_instance().save()
        self.unique_photo_btn.visible = e.control.selected_index == 0
        self.unique_photo_btn.update()

    def account_format_change(self, e):
        Settings.get_instance().account_format = e.control.selected_index
        Settings.get_instance().save()

    def update_threads_text(self, e):
        threads = int(self.threads_slider.value)
        self.threads_label.value = f"Количество потоков ({threads}):"
        self.page.update()
        
        if threads >= 30:
            self.threads_slider.max = 100
        else:
            self.threads_slider.max = 30
        self.threads_slider.update()

    def update_captcha_key(self, e):
        Settings.get_instance().captcha_key = e.control.value
        Settings.get_instance().save()

    def update_asocks_key(self, e):
        Settings.get_instance().asocks_key = e.control.value
        self.asocks_settings.visible = len(Settings.get_instance().asocks_key.strip()) > 0
        self.asocks_key.width = 400 if len(Settings.get_instance().asocks_key.strip()) > 0 else 480
        self.asocks_settings.update()
        self.asocks_key.update()
        Settings.get_instance().save()

    def update_comment_text(self, e):
        threads = int(self.comment_slider.value)
        self.comment_label.value = f"Количество комментов ({threads}):"
        self.page.update()

    def select_accounts(self, e):
        file_path = self.open_file_dialog("Выберите файл с аккаунтами")
        if file_path:
            Settings.get_instance().accounts_file = file_path
            Settings.get_instance().save()

    def select_search_query(self, e):
        file_path = self.open_file_dialog("Выберите файл с текстом для поиска")
        if file_path:
            Settings.get_instance().search_query_file = file_path
            Settings.get_instance().save()

    def select_proxy(self, e):
        file_path = self.open_file_dialog("Выберите файл с прокси")
        if file_path:
            Settings.get_instance().proxies_file = file_path
            Settings.get_instance().save()

    def select_images(self, e):
        file_path = self.open_file_dialog("Выберите картинки", multi=True)
        if file_path:
            Settings.get_instance().images = file_path
            Settings.get_instance().save()

    def select_text(self, e):
        file_path = self.open_file_dialog("Выберите файл с текстом для поста")
        if file_path:
            Settings.get_instance().text_file = file_path
            Settings.get_instance().save()

    def select_post_link(self, e):
        file_path = self.open_file_dialog("Выберите файл с ссылками на пост")
        if file_path:
            Settings.get_instance().posts_file = file_path
            Settings.get_instance().save()

    def start_upload(self, e):
        if e is not None:
            threads = int(self.threads_slider.value)
            comments = int(self.comment_slider.value)
            Settings.get_instance().threads = threads
            Settings.get_instance().comments = comments
        else:
            threads = Settings.get_instance().threads
            comments = Settings.get_instance().comments
        Settings.get_instance().save()

        missing_files = []
        if not os.path.exists(Settings.get_instance().accounts_file):
            missing_files.append("accounts_file")
        if not os.path.exists(Settings.get_instance().proxies_file):
            missing_files.append("proxies_file")
        if not os.path.exists(Settings.get_instance().text_file):
            missing_files.append("text_file")

        if missing_files:
            self.page.snack_bar = ft.SnackBar(ft.Text(f"Missing files: {', '.join(missing_files)}", color=ft.colors.RED))
            self.page.snack_bar.open = True
            self.page.update()
            return

        if len(self.threads_list) == 0:
            self.start_upload_btn.text = "Остановить залив"
            for thread in range(threads):
                process = Process(target=upload_manager, args=(str(Settings.get_instance()), thread))
                process.start()
                self.threads_list.append(process)
        else:
            self.start_upload_btn.text = "Начать залив"
            for thread in self.threads_list:
                thread.terminate()
            self.threads_list.clear()

        self.page.update()

    def open_file_dialog(self, title: str, multi: bool = False) -> str:
        if multi:
            file_path = filedialog.askopenfilenames(title=title)
        else:
            file_path = filedialog.askopenfilename(title=title)
        return file_path

def main(page: ft.Page):
    UploadApp(page)

async def Init_bot(token: str):
    bot = Bot(token=token)
    dp = Dispatcher()
    
    class ActionCallback(CallbackData, prefix="act"):
        action: str
        
    class AccountState(StatesGroup):
        prev_id = State()
    
    @dp.message(F.text == "/start")
    async def start_cmd(msg: types.Message, state: FSMContext):
        await state.clear()
        
        kb1 = types.InlineKeyboardButton(text="🔑 Загрузить аккаунты", callback_data=ActionCallback(action="accounts").pack())
        kb2 = types.InlineKeyboardButton(text="🟢 Запустить залив" if len(UploadApp.instance.threads_list) == 0 else "🔴 Выключить залив", callback_data=ActionCallback(action="upload").pack())
        
        kb = types.InlineKeyboardMarkup(inline_keyboard=[[kb1], [kb2]])
        await msg.answer(f"🎛️ <b>Панель управления</b>\n\nДобро пожаловать! Выберите действие для продолжения.", reply_markup=kb, parse_mode="html")
        
    @dp.callback_query(ActionCallback.filter(F.action == "upload"))
    async def upload_action(query: types.CallbackQuery, callback_data: ActionCallback, state: FSMContext):        
        UploadApp.instance.start_upload(None)
        
        await main_action(query, callback_data, state)
        
    @dp.callback_query(ActionCallback.filter(F.action == "main"))
    async def main_action(query: types.CallbackQuery, callback_data: ActionCallback, state: FSMContext):
        await state.clear()
        await query.answer()
        
        kb1 = types.InlineKeyboardButton(text="🔑 Загрузить аккаунты", callback_data=ActionCallback(action="accounts").pack())
        kb2 = types.InlineKeyboardButton(text="🟢 Запустить залив" if len(UploadApp.instance.threads_list) == 0 else "🔴 Выключить залив", callback_data=ActionCallback(action="upload").pack())
        
        kb = types.InlineKeyboardMarkup(inline_keyboard=[[kb1], [kb2]])
        await query.message.edit_reply_markup(reply_markup=kb)
        
    @dp.callback_query(ActionCallback.filter(F.action == "accounts"))
    async def account_menu(query: types.CallbackQuery, callback_data: ActionCallback, state: FSMContext):
        await state.clear()
        await query.answer()
        
        await state.set_state(AccountState.prev_id)
        await state.update_data(prev_id=query.message.message_id)
        
        kb1 = types.InlineKeyboardButton(text="⬅️ Назад", callback_data=ActionCallback(action="main").pack())
        
        kb = types.InlineKeyboardMarkup(inline_keyboard=[[kb1]])
        await query.message.edit_text(f"📂 Отправьте мне файл или текст с аккаунтами", reply_markup=kb)
        
    @dp.message(AccountState.prev_id)
    async def account_upload_state(message: types.Message, state: FSMContext):
        await message.delete()
        data = await state.get_data()
        await state.clear()
        
        accounts = ""
        
        if message.document:
            file = await bot.get_file(message.document.file_id)
            result = await bot.download_file(file.file_path)
            accounts = result.read().decode()
        else:
            accounts = message.text
        
        with open("C:/Threads/thread/new_accounts.txt", "a", encoding="utf-8") as f:
            f.write(f"\n{accounts}")
        
        acc_len = 0 if not accounts.strip() else len(accounts.strip().split('\n'))
        await bot.edit_message_text(f"📂 Загружено {acc_len} аккаунтов", chat_id=message.chat.id, message_id=data["prev_id"], reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="⬅️ Назад", callback_data=ActionCallback(action="main").pack())]]))
    
    await dp.start_polling(bot)


async def asyncmain():
    if len(Settings.get_instance().telegram_token.strip()) > 0:
        asyncio.create_task(Init_bot(Settings.get_instance().telegram_token.strip()))
    
    await ft.app_async(target=main)

if __name__ == "__main__":
    
    colorama.init()
    
    if not os.path.exists("C:/Threads"):
        os.makedirs("C:/Threads")
    if not os.path.exists("C:/Threads/thread"):
        os.makedirs("C:/Threads/thread")
    # if not os.path.exists("C:/Threads/thread/accounts.db"):
    #     conn = sqlite3.connect("C:/Threads/thread/accounts.db")
    #     conn.cursor().execute("CREATE TABLE IF NOT EXISTS accounts (account TEXT)")
    #     conn.commit()
    #     conn.close()
    if not os.path.exists("C:/Threads/posts.db"):
        conn = sqlite3.connect("C:/Threads/posts.db")
        conn.cursor().execute("CREATE TABLE IF NOT EXISTS posts (id TEXT PRIMARY KEY, repost_count INTEGET DEFAULT 0)")
        conn.commit()
        conn.close()
    if os.path.exists("C:/Threads/logs.txt"): os.remove("C:/Threads/logs.txt")
    
    asyncio.run(asyncmain())
