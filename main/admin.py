from django.contrib import admin
from .models import Category, Tag, Post, Comment


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'category', 'status', 'published_at', 'created_at')
    list_filter = ('status', 'category', 'tags', 'created_at')
    search_fields = ('title', 'excerpt', 'content')
    filter_horizontal = ('tags',)
    date_hierarchy = 'created_at'
    list_editable = ('status',)
    raw_id_fields = ('author',)
    fieldsets = (
        ('Основное', {
            'fields': ('title', 'slug', 'author', 'status')
        }),
        ('Классификация', {
            'fields': ('category', 'tags')
        }),
        ('Содержимое', {
            'fields': ('cover', 'excerpt', 'content')
        }),
        ('Даты', {
            'fields': ('published_at',),
            'classes': ('collapse',),
        }),
    )


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('post', 'author', 'created_at', 'active')
    list_filter = ('active', 'created_at')
    search_fields = ('body', 'author__username', 'post__title')
    list_editable = ('active',)
    raw_id_fields = ('post', 'author')
