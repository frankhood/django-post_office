# -*- coding: utf-8 -*-
# Generated by Django 1.11.5 on 2017-10-05 10:15
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('post_office', '0008_auto_20171004_1633'),
    ]

    operations = [
        migrations.AddField(
            model_name='emailtemplate',
            name='label',
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
