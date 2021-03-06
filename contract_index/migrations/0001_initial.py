# Generated by Django 2.1 on 2021-10-25 06:54

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Index',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('contract_title', models.CharField(db_index=True, max_length=500)),
                ('signing_target_kou', models.CharField(max_length=2000)),
                ('signing_target_otsu', models.CharField(max_length=2000)),
                ('signing_date_disp', models.CharField(blank=True, max_length=200, null=True)),
                ('signing_date', models.DateField(blank=True, db_index=True, null=True)),
                ('expiration_date_disp', models.CharField(blank=True, max_length=200, null=True)),
                ('expiration_date', models.DateField(blank=True, db_index=True, null=True)),
                ('auto_update', models.NullBooleanField()),
                ('file_name', models.CharField(blank=True, db_index=True, max_length=200, null=True)),
                ('pdf_path', models.CharField(blank=True, max_length=2000, null=True)),
                ('remarks', models.CharField(blank=True, max_length=2000, null=True)),
                ('hidden_flag', models.BooleanField(default=False)),
                ('create_date', models.DateTimeField(auto_now_add=True)),
                ('modify_date', models.DateTimeField(auto_now=True)),
                ('deleted_flag', models.BooleanField(default=False)),
                ('create_user', models.CharField(blank=True, max_length=200, null=True)),
                ('modify_user', models.CharField(blank=True, max_length=200, null=True)),
                ('contract_termination_flag', models.BooleanField(default=False)),
                ('contract_companies', models.CharField(default='', max_length=2000)),
                ('original_classification', models.CharField(max_length=200, null=True)),
                ('original_storage_location', models.CharField(max_length=200, null=True)),
                ('loan_guarantee_availability', models.CharField(max_length=200, null=True)),
                ('document_number', models.CharField(max_length=200, null=True)),
                ('storage_location_url', models.CharField(max_length=1000, null=True)),
                ('ringi_url', models.CharField(max_length=1000, null=True)),
                ('ringi_no', models.CharField(max_length=100, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='IndexLocalCompany',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('add_flg', models.IntegerField(default=0)),
                ('index', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='index', to='contract_index.Index')),
            ],
        ),
        migrations.CreateModel(
            name='LocalCompany',
            fields=[
                ('id', models.CharField(max_length=13, primary_key=True, serialize=False)),
                ('local_company_name', models.CharField(max_length=200)),
                ('create_date', models.DateTimeField(auto_now_add=True)),
                ('modify_date', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='RestrictLocalCompany',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('local_company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='restrict_local_company', to='contract_index.LocalCompany')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddField(
            model_name='indexlocalcompany',
            name='local_company',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='local_company', to='contract_index.LocalCompany'),
        ),
        migrations.AddField(
            model_name='index',
            name='localcompanies',
            field=models.ManyToManyField(through='contract_index.IndexLocalCompany', to='contract_index.LocalCompany'),
        ),
    ]
