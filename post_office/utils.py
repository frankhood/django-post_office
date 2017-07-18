# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function, unicode_literals
import logging
import tempfile
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files import File
from django.template.loader import render_to_string
from django.utils import translation
from django.utils.encoding import force_text
from django.utils.translation import (ugettext, ugettext_lazy as _, 
                                      get_language)

from post_office import cache, mail
from .compat import string_types
from .models import Email, PRIORITY, STATUS, EmailTemplate, Attachment
from .settings import get_default_priority
from .validators import validate_email_with_name

logger = logging.getLogger('post_office')

def send_mail(subject, message, from_email, recipient_list, html_message='',
              scheduled_time=None, headers=None, priority=PRIORITY.medium):
    """
    Add a new message to the mail queue. This is a replacement for Django's
    ``send_mail`` core email method.
    """

    subject = force_text(subject)
    status = None if priority == PRIORITY.now else STATUS.queued
    emails = []
    for address in recipient_list:
        emails.append(
            Email.objects.create(
                from_email=from_email, to=address, subject=subject,
                message=message, html_message=html_message, status=status,
                headers=headers, priority=priority, scheduled_time=scheduled_time
            )
        )
    if priority == PRIORITY.now:
        for email in emails:
            email.dispatch()
    return emails


def get_email_template(name, language=''):
    """
    Function that returns an email template instance, from cache or DB.
    """
    use_cache = getattr(settings, 'POST_OFFICE_CACHE', True)
    if use_cache:
        use_cache = getattr(settings, 'POST_OFFICE_TEMPLATE_CACHE', True)
    if not use_cache:
        return EmailTemplate.objects.get(name=name, language=language)
    else:
        composite_name = '%s:%s' % (name, language)
        email_template = cache.get(composite_name)
        if email_template is not None:
            return email_template
        else:
            email_template = EmailTemplate.objects.get(name=name,
                                                       language=language)
            cache.set(composite_name, email_template)
            return email_template


def split_emails(emails, split_count=1):
    # Group emails into X sublists
    # taken from http://www.garyrobinson.net/2008/04/splitting-a-pyt.html
    # Strange bug, only return 100 email if we do not evaluate the list
    if list(emails):
        return [emails[i::split_count] for i in range(split_count)]


def create_attachments(attachment_files):
    """
    Create Attachment instances from files

    attachment_files is a dict of:
        * Key - the filename to be used for the attachment.
        * Value - file-like object, or a filename to open OR a dict of {'file': file-like-object, 'mimetype': string}

    Returns a list of Attachment objects
    """
    attachments = []
    for filename, filedata in attachment_files.items():

        if isinstance(filedata, dict):
            content = filedata.get('file', None)
            mimetype = filedata.get('mimetype', None)
        else:
            content = filedata
            mimetype = None

        opened_file = None

        if isinstance(content, string_types):
            # `content` is a filename - try to open the file
            opened_file = open(content, 'rb')
            content = File(opened_file)

        attachment = Attachment()
        if mimetype:
            attachment.mimetype = mimetype
        attachment.file.save(filename, content=content, save=True)

        attachments.append(attachment)

        if opened_file is not None:
            opened_file.close()

    return attachments


def parse_priority(priority):
    if priority is None:
        priority = get_default_priority()
    # If priority is given as a string, returns the enum representation
    if isinstance(priority, string_types):
        priority = getattr(PRIORITY, priority, None)

        if priority is None:
            raise ValueError('Invalid priority, must be one of: %s' %
                             ', '.join(PRIORITY._fields))
    return priority


def parse_emails(emails):
    """
    A function that returns a list of valid email addresses.
    This function will also convert a single email address into
    a list of email addresses.
    None value is also converted into an empty list.
    """

    if isinstance(emails, string_types):
        emails = [emails]
    elif emails is None:
        emails = []

    for email in emails:
        try:
            validate_email_with_name(email)
        except ValidationError:
            raise ValidationError('%s is not a valid email address' % email)

    return emails





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
        template_temp = create_temporary_file('project/templates/mails', content.encode("utf8"))
        content_rendered = render_to_string(template_temp.name, context)
        template_temp.close()
        
        return content_rendered
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

