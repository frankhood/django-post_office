# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django import forms
from django.db import models
from django.contrib import admin
from django.conf import settings
from django.forms.widgets import TextInput
from django.template.defaultfilters import safe
from django.utils import six
from django.utils.html import strip_spaces_between_tags, escape
from django.utils.safestring import mark_safe
from django.utils.text import Truncator
from django.utils.translation import ugettext, ugettext_lazy as _

from fhcore.apps.db.admin.mixins import (
    ConfigurableWidgetsMixinAdmin, FixtureAdminMixin)

from .fields import CommaSeparatedEmailField
from .models import Attachment, Log, Email, EmailTemplate, STATUS
from .preview_utils import (add_style_inline,
                    POSTOFFICE_TAGS_STYLES, 
                    render_to_temporary_file,
                    POSTOFFICE_TEMPLATE_LIBS_TO_LOAD)




class LogInline(admin.StackedInline):
    model = Log
    extra = 0

class AttachmentInline(admin.TabularInline):
    #model=Email.attachments.through
    model=Attachment.emails.through
    readonly_fields = ('display_attachment',)
    fields = ('display_attachment',)
    #fields = ('name', 'file', )
    extra=0
    
    def display_attachment(self,obj):
        if obj:
            return '<a href="{obj.attachment.file.url}" target="_blank">{obj.attachment.name}</a>'.format(obj=obj)
        return '---'
    display_attachment.allow_tags= True


class CommaSeparatedEmailWidget(TextInput):

    def __init__(self, *args, **kwargs):
        super(CommaSeparatedEmailWidget, self).__init__(*args, **kwargs)
        self.attrs.update({'class': 'vTextField'})

    def _format_value(self, value):
        # If the value is a string wrap it in a list so it does not get sliced.
        if not value:
            return ''
        if isinstance(value, six.string_types):
            value = [value, ]
        return ','.join([item for item in value])



class EmailAdmin(admin.ModelAdmin):
    list_display = ('id', 'to_display', 'subject', 'template',
                    'status', 'last_updated')
    list_filter = ['status', 'template',]
    search_fields = ('to','subject')
    readonly_fields = ("display_mail_preview",)

    actions = ['requeue', 'set_as_sent']
    inlines = [LogInline, AttachmentInline]
    
    fieldsets = (
            (None, {'fields': (
                ('subject','from_email', ),
                ('to', "cc","bcc",),
                ('html_message',),
                ('display_mail_preview',),
                ('status','priority',),
            )}),
        )
    
    formfield_overrides = {
        CommaSeparatedEmailField: {'widget': CommaSeparatedEmailWidget}
    }
    def get_queryset(self, request):
        return super(EmailAdmin, self).get_queryset(request).select_related('template')

    def to_display(self, instance):
        return ', '.join(instance.to)
    to_display.short_description = ugettext('to')
    to_display.admin_order_field = 'to'
    
    def display_mail_preview(self,obj):
        content = safe(obj.html_message)
        return strip_spaces_between_tags(mark_safe("<div style='width:860px; '><iframe width='100%' height='350px' srcdoc='{mail_message}'>PREVIEW</iframe></div>\
                    ".format(**{'mail_message':escape(strip_spaces_between_tags(content))})))
    display_mail_preview.allow_tags=True
    display_mail_preview.short_description=ugettext("Preview")
    
    def set_as_sent(modeladmin, request, queryset):
        """An admin action to set as sent emails."""
        queryset.update(status=STATUS.sent)
    set_as_sent.short_description = ugettext('Set as Sent selected emails')
    
    def requeue(modeladmin, request, queryset):
        """An admin action to requeue emails."""
        queryset.update(status=STATUS.queued)
    requeue.short_description = ugettext('Requeue selected emails')

class LogAdmin(admin.ModelAdmin):
    list_display = ('date', 'email', 'status', 'get_message_preview')
    
    def get_message_preview(instance):
        return (u'{0}...'.format(instance.message[:25]) if len(instance.message) > 25
                else instance.message)
    get_message_preview.short_description = ugettext('Message')

class SubjectField(TextInput):
    def __init__(self, *args, **kwargs):
        super(SubjectField, self).__init__(*args, **kwargs)
        self.attrs.update({'style': 'width: 610px;'})

class EmailTemplateAdminForm(forms.ModelForm):
 
    language = forms.ChoiceField(choices=settings.LANGUAGES, required=False, 
                                 help_text=_("Render template in alternative language"),
                                 label=_("Language"))
 
    class Meta:
        model = EmailTemplate
        fields = ('name', 'description', 'subject',
                  'content', 'html_content', 'language', 'default_template')


class EmailTemplateInline(admin.StackedInline):
    form = EmailTemplateAdminForm
    model = EmailTemplate
    extra = 0
    fields = ('language', 'subject', 'content', 'html_content',)
    formfield_overrides = {
        models.CharField: {'widget': SubjectField}
    }

    def get_max_num(self, request, obj=None, **kwargs):
        return len(settings.LANGUAGES)


class EmailTemplateAdmin(FixtureAdminMixin,
                        ConfigurableWidgetsMixinAdmin,  
                         admin.ModelAdmin):
    form = EmailTemplateAdminForm
    list_display = ('name', 'description_shortened', 'subject', 'created')
    #list_display = ('name', 'description_shortened', 'subject', 'languages_compact', 'created')
    search_fields = ('name', 'description', 'subject')
    
    #inlines = (EmailTemplateInline,) if settings.USE_I18N else ()
    inlines = []
    save_as=True
    readonly_fields = ('mail_preview',)
        
    
    fieldsets = [
            (_("Settings"), { 'fields': (
                    ('name',),# 'language'),
                    ('description', )
            ),}),
            ('Email', { 'fields':(
                    ('subject',), 
                    ('content',),
            ),}),
            ('Preview', { 'fields': (
                    'mail_preview',
            ),}),
            ('Developer data', {
                'classes': ('collapse',),
                'fields': ('html_content',),
            }),
        ]
    #===========================================================================
    # fieldsets = [
    #     (None, {
    #         'fields': ('name', 'description'),
    #     }),
    #     (_("Default Content"), {
    #         'fields': ('subject', 'content', 'html_content'),
    #     }),
    # ]
    #===========================================================================
        
    formfield_overrides = {
        models.CharField: {'widget': SubjectField}
    }
    
    dbfield_overrides = {
        'name':{'help_text':_("Do not change this field! It is for internal use only"),
                'label':_("ID"),
                'required': True
        },
        'subject':{'label':_("Mail Subject"),},
        'content':{
           #'widget':CKEditorWidget(),#config_name='noimage_ckeditor'),
           'label':_("Mail Body"),
           'help_text':_("The fields between '{{' and '}}' are the variables while "
                         "the text that is included in the tags "
                         "'{% comment%}' and '{% endcomment%}' will not be rendered "
                         " in the mail "
                         "<br/> Do not remove the fields included in the tags '{%' '%}'"),
        },
        #'content_it':{'label':"Corpo della mail [ IT ]"},
        #'content_en':{'label':"Corpo della mail [ EN ]"},
        'html_content':{
            'help_text':_("The fields between '{{' and '}}' are the variables while "
                         "the text that is included in the tags "
                         "'{% comment%}' and '{% endcomment%}' will not be rendered "
                         " in the mail "
                         "<br/> Do not remove the fields included in the tags '{%' '%}'"),
        },
    }
    

    def get_queryset(self, request):
        return self.model.objects.filter(default_template__isnull=True)

    def description_shortened(self, instance):
        return Truncator(instance.description.split('\n')[0]).chars(200)
    description_shortened.short_description = _("Description")
    description_shortened.admin_order_field = 'description'

    def languages_compact(self, instance):
        languages = [tt.language for tt in instance.translated_templates.all()]
        return ', '.join(languages)
    languages_compact.short_description = _("Languages")


    def mail_preview(self,obj=None):
        content_preview = add_style_inline(obj.content, POSTOFFICE_TAGS_STYLES)
        content_preview = content_preview.replace('{{', '{').replace('}}', '}')
        context = {}
        content_preview = POSTOFFICE_TEMPLATE_LIBS_TO_LOAD+content_preview
        content_preview = render_to_temporary_file(content_preview, context)
        context.update({'content':content_preview})
        html_content_preview = render_to_temporary_file(obj.html_content, context)
        help_text = '<div class="help">%s</div>' % (_('*I dati in questa preview sono fittizzi e del tutto casuali'))
        return strip_spaces_between_tags(mark_safe("{help_text}<div style='width:860px; height:500px;'><iframe style='margin-left:107px;' width='97%' height='480px' srcdoc='{mail_message}'>PREVIEW</iframe></div>\
                    ".format(**{'help_text':help_text,
                                'mail_message':escape(strip_spaces_between_tags(html_content_preview))})))
    mail_preview.allow_tags=True
    mail_preview.short_description=_("Preview")
    
    def get_fixture_filename(self):
        fixture_dirname = os.path.join('project', 'core', 'fixtures')
        try:
            os.stat(fixture_dirname)
        except:
            os.mkdir(fixture_dirname)
        return os.path.join(fixture_dirname,
                            'emailtemplates_{0}.json'.format(formats.date_format(timezone.now(),"Ymd_Hi"))
                            )
        
    #===========================================================================
    # def mail_preview(self, content="", html_content=""):
    #     content_preview = add_style_inline(content, POSTOFFICE_TAGS_STYLES)
    #     content_preview = content_preview.replace('{{', '{').replace('}}', '}')
    #     context = {}
    #     content_preview = POSTOFFICE_TEMPLATE_LIBS_TO_LOAD+content_preview
    #     content_preview = render_to_temporary_file(content_preview, context)
    #     context.update({'content':content_preview})
    #     html_content_preview = render_to_temporary_file(html_content, context)
    #     help_text = '<div class="help">%s</div>' % (_('*Tha data in this Preview are fake and random'))
    #     return strip_spaces_between_tags(mark_safe("{help_text}<div style='width:860px; height:500px;'><iframe style='margin-left:107px;' width='97%' height='480px' srcdoc='{mail_message}'>PREVIEW</iframe></div>\
    #                 ".format(**{'help_text':help_text,
    #                             'mail_message':escape(strip_spaces_between_tags(html_content_preview))})))
    # 
    # def mail_preview_it(self,obj=None):
    #     return self.mail_preview(obj.content_it,obj.html_content)
    # mail_preview_it.allow_tags=True
    # mail_preview_it.short_description="{0} [IT]".format(_("Preview"))
    # 
    # def mail_preview_en(self,obj=None):
    #     return self.mail_preview(obj.content_en,obj.html_content)
    # mail_preview_en.allow_tags=True
    # mail_preview_en.short_description="{0} [EN]".format(_("Preview"))
    #===========================================================================
    
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'file', )


admin.site.register(Email, EmailAdmin)
admin.site.register(Log, LogAdmin)
admin.site.register(EmailTemplate, EmailTemplateAdmin)
admin.site.register(Attachment, AttachmentAdmin)
