from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView,
)
from django.views.generic.edit import FormMixin

from .forms import CommentForm, SignUpForm
from .models import Post, Category, Tag
from django.contrib.admin.views.decorators import staff_member_required

from .importer import import_news_to_django, SITES


class PostListView(ListView):
    model = Post
    template_name = 'main/post_list.html'
    context_object_name = 'posts'
    paginate_by = 6

    def get_queryset(self):
        qs = Post.objects.filter(status='published').select_related(
            'author', 'category'
        ).prefetch_related('tags')

        query = self.request.GET.get('q')
        if query:
            qs = qs.filter(
                Q(title__icontains=query) |
                Q(excerpt__icontains=query) |
                Q(content__icontains=query)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('q', '')
        return context


class PostDetailView(FormMixin, DetailView):
    model = Post
    template_name = 'main/post_detail.html'
    context_object_name = 'post'
    form_class = CommentForm

    def get_queryset(self):
        qs = Post.objects.select_related('author', 'category').prefetch_related(
            'tags', 'comments__author'
        )
        if self.request.user.is_staff:
            return qs
        return qs.filter(status='published')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['comments'] = self.object.comments.filter(active=True).select_related('author')
        context['form'] = self.get_form()
        return context

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, 'Войдите, чтобы оставить комментарий.')
            return redirect('post_detail', slug=self.get_object().slug)

        self.object = self.get_object()
        form = self.get_form()
        if form.is_valid():
            comment = form.save(commit=False)
            comment.post = self.object
            comment.author = request.user
            comment.save()
            messages.success(request, 'Комментарий добавлен.')
            return redirect('post_detail', slug=self.object.slug)
        return self.render_to_response(self.get_context_data(form=form))


class CategoryDetailView(ListView):
    model = Post
    template_name = 'main/post_list.html'
    context_object_name = 'posts'
    paginate_by = 6

    def get_queryset(self):
        self.category = Category.objects.get(slug=self.kwargs['slug'])
        return Post.objects.filter(
            status='published', category=self.category
        ).select_related('author', 'category').prefetch_related('tags')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Категория: {self.category.name}'
        return context


class TagDetailView(ListView):
    model = Post
    template_name = 'main/post_list.html'
    context_object_name = 'posts'
    paginate_by = 6

    def get_queryset(self):
        self.tag = Tag.objects.get(slug=self.kwargs['slug'])
        return Post.objects.filter(
            status='published', tags=self.tag
        ).select_related('author', 'category').prefetch_related('tags')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Тег: {self.tag.name}'
        return context


class PostCreateView(LoginRequiredMixin, CreateView):
    model = Post
    template_name = 'main/post_form.html'
    fields = ['title', 'category', 'tags', 'cover', 'excerpt', 'content', 'status']

    def form_valid(self, form):
        form.instance.author = self.request.user
        messages.success(self.request, 'Статья создана.')
        return super().form_valid(form)


class PostUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Post
    template_name = 'main/post_form.html'
    fields = ['title', 'category', 'tags', 'cover', 'excerpt', 'content', 'status']

    def test_func(self):
        post = self.get_object()
        return self.request.user == post.author or self.request.user.is_staff

    def form_valid(self, form):
        messages.success(self.request, 'Статья обновлена.')
        return super().form_valid(form)


class PostDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Post
    template_name = 'main/post_confirm_delete.html'
    success_url = reverse_lazy('post_list')

    def test_func(self):
        post = self.get_object()
        return self.request.user == post.author or self.request.user.is_staff

    def form_valid(self, form):
        messages.success(self.request, 'Статья удалена.')
        return super().form_valid(form)


class SignUpView(CreateView):
    form_class = SignUpForm
    template_name = 'main/signup.html'
    success_url = reverse_lazy('post_list')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('post_list')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        messages.success(self.request, 'Добро пожаловать!')
        return response


class CustomLoginView(LoginView):
    template_name = 'main/login.html'
    redirect_authenticated_user = True


class LogoutView(View):
    def post(self, request):
        logout(request)
        messages.success(request, 'Вы вышли из аккаунта.')
        return redirect('post_list')

    def get(self, request):
        return self.post(request)


@staff_member_required
def admin_import_news(request):
    """Запускает парсинг новостей из выбранного источника (только для стаффа)."""
    if request.method != "POST":
        return redirect('/admin/main/post/')

    site = request.POST.get('site', 'lenta')

    if site not in SITES:
        messages.error(request, f'Сайт "{site}" не поддерживается.')
        return redirect('/admin/main/post/')

    try:
        import_news_to_django(site_key=site, author_username=request.user.username)
        messages.success(
            request,
            f'✅ Импорт с {SITES[site]["name"]} завершён. Проверьте черновики ниже.'
        )
    except Exception as e:
        messages.error(request, f'❌ Ошибка импорта: {e}')

    return redirect('/admin/main/post/?status__exact=draft')    
