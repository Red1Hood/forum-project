import json
import google.generativeai as genai
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from django.contrib.auth.decorators import login_required
from .forms import PostForm, CommentForm, RegisterForm
from django.contrib.auth import authenticate, login, logout
# Дважды импортировал login_required, на всякий
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.shortcuts import render, get_object_or_404
from .models import Post


def home(request):
    # Достал все посты и сразу отсортировал по дате, чтобы новые были сверху
    posts = Post.objects.order_by('-created_at')

    return render(
        request,
        'forum/home.html',
        {'posts': posts}
    )


def post_detail(request, post_id):
    # Поиск поста. Если кто-то введет кривой ID в адресную строку - выдаст 404, а не сломает сайт
    post = get_object_or_404(Post, id=post_id)

    if request.method == 'POST':

        form = CommentForm(request.POST)

        if form.is_valid():
            
            # Защита: если юзер как-то отправил POST-запрос без авторизации - кидаем его на логин
            if not request.user.is_authenticated:
                return redirect('login')

            # commit=False нужен, чтобы форма пока не улетала в БД, так как там не хватает автора и поста
            comment = form.save(commit=False)
            comment.post = post
            comment.author = request.user
            
            # Теперь всё на месте, можно сохранять
            comment.save()

            # Перезагружаем страницу поста, чтобы коммент появился
            return redirect(
                'post_detail',
                post_id=post.id
            )

    else:
        form = CommentForm()

    # Достаем все комментарии, которые привязаны к этому конкретному посту
    comments = post.comment_set.all()

    return render(
        request,
        'forum/post_detail.html',
        {
            'post': post,
            'comments': comments,
            'form': form
        }
    )

@login_required
def create_post(request):

    if request.method == 'POST':
        form = PostForm(request.POST)

        if form.is_valid():
             # Снова commit=False, чтобы вручную подцепить текущего юзера как автора темы
             post = form.save(commit=False)
             post.author = request.user
             post.save()
             return redirect('home')

    else:
        form = PostForm()

    return render(
        request,
        'forum/create_post.html',
        {'form': form}
    )

def edit_post(request, post_id):

    post = get_object_or_404(Post, id=post_id)
    
    # Защита от умников: если чужой юзер попытается зайти по ссылке редактирования, выкидываем на главную
    if request.user != post.author:
     return redirect('home')

    if request.method == 'POST':
        # instance=post означает, что мы не создаем новую тему, а перезаписываем старую
        form = PostForm(request.POST, instance=post)

        if form.is_valid():
            form.save()
            return redirect('post_detail', post_id=post.id)

    else:
        # Закидываем старые данные поста в форму, чтобы юзеру не пришлось писать всё заново
        form = PostForm(instance=post)

    return render(
        request,
        'forum/edit_post.html',
        {
            'form': form,
            'post': post
        }
    )

def delete_post(request, post_id):

    post = get_object_or_404(Post, id=post_id)

    # Тоже проверяем, чтобы кто попало не удалял чужие посты
    if request.user != post.author:
     return redirect('home')

    # Удаляем ТОЛЬКО через POST-запрос (по нажатию кнопки). Просто переход по ссылке не должен ничего удалять
    if request.method == 'POST':
        post.delete()
        return redirect('home')

    return render(
        request,
        'forum/delete_post.html',
        {'post': post}
    )

def register(request):

    if request.method == 'POST':
        form = RegisterForm(request.POST)

        if form.is_valid():
            user = form.save()
            # Сразу логиним пользователя после успешной регистрации
            login(request, user)

            return redirect('home')

    else:
        form = RegisterForm()

    return render(
        request,
        'forum/register.html',
        {'form': form}
    )

def user_login(request):

    if request.method == 'POST':
        
        # Тут проверяем логин вручную, берем данные прямо из POST-запроса
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None:
            login(request, user)
            return redirect('home')

    return render(request, 'forum/login.html')

def user_logout(request):

    logout(request)

    return redirect('home')

# csrf_exempt нужен, чтобы JS мог отправлять запросы без CSRF-токена, иначе заморочек много
@csrf_exempt 
def ask_ai(request):
    if request.method == "POST":
        try:
            # 1. Ловим вопрос от пользователя
            data = json.loads(request.body)
            user_message = data.get("message", "")

            # 2. ДИНАМИЧЕСКАЯ ИНФОРМАЦИЯ ИЗ БД (Статистика)
            total_posts = Post.objects.count()
            latest_posts = Post.objects.order_by('-created_at')[:5]
            post_titles = ", ".join([post.title for post in latest_posts])
            if not post_titles:
                post_titles = "Тем пока нет, форум пустой."

            # 3. РАСШИРЕННАЯ "ШПАРГАЛКА" (БАЗА ЗНАНИЙ ДЛЯ ИИ)
            context_prompt = f"""
            Ты — дружелюбный, умный и полезный ИИ-ассистент нашего форума. 
            Твоя задача — консультировать пользователей по работе сайта и отвечать на их вопросы.

            Вот актуальная статистика форума прямо сейчас:
            - Всего создано тем: {total_posts}
            - Названия последних тем: {post_titles}

            ИНСТРУКЦИЯ ПО ИСПОЛЬЗОВАНИЮ ФОРУМА (используй это, если пользователь спрашивает, как что-то сделать):
            1. Чтение: Читать форум могут все желающие, регистрация для этого не нужна.
            2. Регистрация и Вход: Чтобы создать тему или написать комментарий, нужно войти в аккаунт (кнопка "Войти" на главной) или зарегистрироваться ("Регистрация").
            3. Создание темы: Авторизованный пользователь может нажать зеленую кнопку "Создать тему" на главной странице, заполнить заголовок, выбрать категорию и написать текст.
            4. Комментарии: Чтобы прокомментировать пост, нужно открыть его (кнопка "Читать полностью"), пролистать в самый низ и написать текст в форму.
            5. Редактирование и Удаление: Пользователь может редактировать или удалять ТОЛЬКО СВОИ собственные темы. Кнопки "Редактировать" (желтая) и "Удалить" (красная) находятся внутри поста, прямо под текстом автора. Чужие темы удалять нельзя.

            ПРАВИЛА ОБЩЕНИЯ И ФОРМАТ ОТВЕТА:
            - Отвечай кратко, понятно и вежливо. Не пиши огромные простыни текста.
            - Если пользователь спрашивает, как удалить пост — объясни ему правило №5.
            - Если спрашивает, почему не может оставить комментарий — напомни про правило №2 (нужно войти в аккаунт).
            - Если пользователь задает отвлеченный вопрос (например, "Кто такой Зевс?" или "Как написать код на Python?"), ответь на вопрос как обычно, но можешь дружелюбно предложить создать об этом тему на нашем форуме.

            Вопрос пользователя: {user_message}
            """

            # 4. Отправляем запрос в Google
            genai.configure(api_key="ТВОЙ_КЛЮЧ_ЗДЕСЬ") 
            # Используем актуальную и быструю модель
            model = genai.GenerativeModel('gemini-3.5-flash')
            
            response = model.generate_content(context_prompt)
            
            # Возвращаем ответ на сайт
            return JsonResponse({"reply": response.text})

        except Exception as e:
            return JsonResponse({"reply": f"Ой, ошибка: {str(e)}"}, status=500)

    return JsonResponse({"reply": "Неверный метод запроса."})
