# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function, unicode_literals
import logging
import tempfile
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files import File
from django.template.loader import render_to_string
from django.template import Template, Context
from django.utils import translation
from django.utils.encoding import force_text
from django.utils.translation import (ugettext, ugettext_lazy as _, 
                                      get_language)

from post_office import mail
from .models import Email, EmailTemplate

logger = logging.getLogger('post_office')

#===============================================================================
# CUSTOM CODE
#===============================================================================


def create_temporary_file(dir=None, content=''):
    file_temp = tempfile.NamedTemporaryFile(mode='w+b',dir=dir)
    file_temp.write(content)
    file_temp.seek(0)
    
    return file_temp

def render_to_temporary_file(content='', context=None):
    try:
        #content = unicode(content, "ascii")
        #-----------------------------------------------------------------------
        # template_temp = create_temporary_file('project/templates/mails', content.encode("utf8"))
        # content_rendered = render_to_string(template_temp.name, context)
        # template_temp.close()
        # 
        # return content_rendered
        #-----------------------------------------------------------------------
        
        inmemory_template = Template(content.encode("utf8"))
        if isinstance(context, Context):
            return inmemory_template.render(context)
        else:
            return inmemory_template.render(Context(context))
    except UnicodeEncodeError as ex:
        logger.exception("Unicode error")
        return "La preview non e\' disponibile"
    except Exception as ex:
        logger.exception("Si e' verificato un errore")
        return "La preview non e\' disponibile"
    

def add_style_inline(content, tag_styles):
    for tag, style in tag_styles.iteritems():
        content = content.replace(tag.lower(), style)
        content = content.replace(tag.upper(), style)
    return content


MODS_EMAILS = getattr(settings, 'MODS_EMAILS', ['info@example.com'])

POSTOFFICE_TEMPLATE_LIBS_TO_LOAD_DEFAULT = '<p>{% load i18n %}{% load static from staticfiles %}</p>'
POSTOFFICE_TEMPLATE_LIBS_TO_LOAD = getattr(settings, 
                                           'POSTOFFICE_TEMPLATE_LIBS_TO_LOAD', 
                                           POSTOFFICE_TEMPLATE_LIBS_TO_LOAD_DEFAULT)

POSTOFFICE_TAGS_STYLES_DEFAULT = {
    '<p>': '<p style="font-size: 16px; line-height: 26px">',
    '<h2>': '<h2 style="font-size:20px; line-height:26px; font-weight:normal">',
    #'<a ':'<a style="color:#EC008C;text-decoration: none;" ',
    '<a>':'<a style="color:#EC008C; text-decoration: none;">',
    '<ul>':'<ul style="font-size: 16px;line-height: 26px;padding-left:20px">',
}
POSTOFFICE_TAGS_STYLES = getattr(settings, 
                                        'POSTOFFICE_TAGS_STYLES', 
                                        POSTOFFICE_TAGS_STYLES_DEFAULT)

def send_postoffice_email(to_email, from_email, context,
                          subject_template_name,email_template_name,
                          postoffice_template_name=None,
                          language=None, attachments = {},
                          bcc=list(MODS_EMAILS)):
    
    if not to_email:
        logger.warning("Non invio la mail perchè non c'è una mail a cui inviarla!")
        return
    
    def send_templated_email(to_email, from_email, context,
                             email_template, attachments = {},
                             bcc=list(MODS_EMAILS)):
        email_template.content = POSTOFFICE_TEMPLATE_LIBS_TO_LOAD + email_template.content
        content_preview = render_to_temporary_file(add_style_inline(email_template.content, settings.POSTOFFICE_TAGS_STYLES), context)
        context.update({'content':content_preview})
        mail_template_attachments = None if (not email_template.attachment_templates) else email_template.attachment_templates.all()
        attachments = attachments or {}
        if not attachments:
            attachments = {}
            for attachment in mail_template_attachments:
                attachments.update({attachment.name: attachment.file})
        mail.send(to_email,
              from_email,
              template=email_template,
              context=context,
              # headers=headers,
              bcc=bcc,
              attachments=attachments)
    
    def send_normal_email(to_email, from_email, context,
                          subject_template_name,email_template_name,
                          attachments = {},
                          bcc=list(MODS_EMAILS)):
        subject = render_to_string(subject_template_name, context)
        subject = ''.join(subject.splitlines())
        message = render_to_string(email_template_name, context)
        mail.send(to_email,
              from_email,
              subject=subject,
              html_message=message,
              bcc=bcc,
              attachments=attachments)
        
    mail_sent=False
    old_language = translation.get_language()
    translation_language=language
    try:
        if postoffice_template_name:
            email_template = EmailTemplate.objects.get(name=postoffice_template_name)
            if translation_language:
                with translation.override(translation_language, deactivate=True):
                    send_templated_email(to_email, from_email, context,
                                         email_template = email_template, attachments = attachments,
                                         bcc=bcc)
                translation.activate(old_language)
            else:
                send_templated_email(to_email, from_email, context,
                                         email_template = email_template, attachments = attachments,
                                         bcc=bcc)
            mail_sent=True
    except EmailTemplate.DoesNotExist:
        logger.warning("Attenzione!! EmailTemplate con name :%s non trovato"%postoffice_template_name)
    if not mail_sent:
        if translation_language:
            with translation.override(translation_language, deactivate=True):
                send_normal_email(to_email, from_email, context,
                                  subject_template_name,email_template_name,
                                  attachments = attachments,
                                  bcc=bcc)
            translation.activate(old_language)
        else:
            send_normal_email(to_email, from_email, context,
                          subject_template_name,email_template_name,
                                  attachments = attachments,
                                  bcc=bcc)

def get_variables_from_content(content):
    content_split = content.rsplit('{{')
    variables = []
    for c in content_split:
        try:
            print(c)
            if c.index('}}'):
                variables.append(c.rsplit('}}')[0])
        except ValueError:
            pass
    return variables

def check_add_extra_fieldset(fieldsets, variables):
    for idx, field in enumerate(fieldsets):
        if field[0] ==  'Preview parameters':
            break
        if field[0] ==  'Preview':
            fieldsets.insert((idx), (u'Preview parameters', {
                                            'classes': ('collapse',), 
                                            'fields': tuple(variables)}))
            break