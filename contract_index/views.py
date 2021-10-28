import ast
import csv
import io
import json
import logging
import math
import os
import re
from datetime import date, timedelta
from io import StringIO, TextIOWrapper
from django.db import transaction
from django.core import serializers
import base64
from django import db
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import models
from django.db.models import Prefetch, Q, Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import six
import json
from querystring_parser import parser
from collections import OrderedDict
import pprint

# 高速化テスト
# from numba import jit

# from .models import Company
from .models import (Index, IndexLocalCompany, LocalCompany,
                     RestrictLocalCompany)
from .cc_query_helper import make_cc_query, make_cn_query

def original_classification_dict():
    """
    項目「原本区分」の辞書を返します
    """
    return {'1': '紙', '2': 'CS', '3': 'GMO Agree', '4': 'DocuSign', '5': 'データ（クラウドサイン）'}


def original_storage_location_dict():
    """
    項目「原本保管場所」の辞書を返します
    """
    return {'1': '法務部', '2': 'データ保管', '3': '人事管理（出向系）'}


def add_condition(order_dict, key, condition):
    if key in order_dict:
        if isinstance(condition, list):
            order_dict[key] += condition
        else:
            order_dict[key] += ',' + condition
    else:
        order_dict[key] = condition

def isalnum_ascii(s):
    return s.isalnum() and len(s) == len(s.encode())

def check_pc_number(s):
    return isalnum_ascii(s) and len(s) == 13

# 各ページへの遷移処理 ---------------------------------------------------------------------

@login_required
def index(request):
    """
    idexへの遷移です。
    """

    info("START1")

    indexes = Index.objects.filter(deleted_flag=False)
    # スーパーユーザでなければ管轄社で表示を絞る
    if not request.user.is_superuser:
        # 管轄社の処理
        lc_list = list()
        src_list = list()
        # 新形式 2019/05/21
        rlc = RestrictLocalCompany.objects.filter(user_id=request.user.id)
        if rlc:
            for r in rlc:
                src_list.append(r.local_company_id)

            for i in IndexLocalCompany.objects.filter(local_company_id__in=src_list):
                lc_list.append(i.index_id)
            indexes = indexes.filter(id__in=lc_list)
    # hidden_flagの処理
    if not request.user.has_perm('contract_index.view_hidden'):
        indexes = indexes.filter(hidden_flag=False)
    # 管轄社カラム用
    if request.user.has_perm('contract_index.read_localcompany'):
        indexes = indexes.prefetch_related('localcompanies')

    content = {
        'name': request.user,
        # 削除フラグは取得しない
        # 'indexes': Index.objects.all(),
        'indexes': indexes,
        'indexes_localCompanies': IndexLocalCompany.objects.all(),
        'result': None,
        'original_classification_dict': original_classification_dict().items(),
        'original_storage_location_dict': original_storage_location_dict().items(),
    }
    return render(request, 'contract_index/index.html', content)


@login_required
def search(request):
    """
    検索への遷移です。
    """
    content = {
        'name': request.user,
        'result': None,
        'localCompanies': LocalCompany.objects.all().order_by('local_company_name'),
        'original_classification_dict': original_classification_dict().items(),
        'original_storage_location_dict': original_storage_location_dict().items(),
    }
    return render(request, 'contract_index/search.html', content)


@login_required
def addrecord(request):
    """
    レコード追加への遷移です。
    """
    
    if request.method == "POST":
        # 管轄社番号のチェック        
        lc_list = request.POST['local_company_number'].split(",")
        if lc_list:
            for lc in lc_list:
                if lc:
                    if not check_pc_number(lc.strip()):
                        content = {
                            'name': request.user,
                            'indexes': [],
                            'indexes_localCompanies': [],
                            'localCompanies': LocalCompany.objects.all().order_by('local_company_name'),
                            'result': "管轄社番号を正しく入力してください",
                            'original_classification_dict': original_classification_dict().items(),
                            'original_storage_location_dict': original_storage_location_dict().items(),
                            'old': request.POST
                        }
                        return render(request, 'contract_index/addrecord.html', content)

        # 日付の精査処理
        # 締結日
        signing_date = ''
        signing_date_disp = ''
        if request.POST['signing_date_y']:
            signing_date_disp += request.POST['signing_date_y']
            if request.POST['signing_date_m']:
                signing_date_disp += '-' + request.POST['signing_date_m']
                if request.POST['signing_date_d']:
                    signing_date_disp += '-' + request.POST['signing_date_d']
                    signing_date = signing_date_disp
                else:
                    signing_date = signing_date = signing_date_disp + '-01'
            else:
                signing_date = signing_date_disp + '-01-01'
        else:
            signing_date_disp = ''
            signing_date = None

        # 有効期限
        expiration_date = None
        expiration_date_disp = ''

        auto_update = None

        # 非開示フラグ

        hidden_flag = 0
        pdf_path = ''
        if request.POST.get('hidden_flag') == 'true':
            hidden_flag = 1
        if request.POST.get('pdf_path'):
            pdf_path = request.POST['pdf_path']

        # 相手先法人番号
        number_array = request.POST['partner_corporate_number'].strip().split(",")
        modified_val = []
        for number_item in number_array:                            
            if not check_pc_number(number_item.strip()):
                content = {
                    'name': request.user,
                    'indexes': [],
                    'indexes_localCompanies': [],
                    'localCompanies': LocalCompany.objects.all().order_by('local_company_name'),
                    'result': "相手先法人番号を正しく入力してください",
                    'original_classification_dict': original_classification_dict().items(),
                    'original_storage_location_dict': original_storage_location_dict().items(),
                    'old': request.POST
                }
                return render(request, 'contract_index/addrecord.html', content)
            modified_val.append(number_item.strip())
        partner_corporate_number = ",".join(modified_val)

        Index(
            pdf_path=pdf_path,
            contract_title=zenhan(request.POST['contract_title']),
            signing_target_kou='',
            signing_target_otsu='',
            contract_companies=zenhan(request.POST['contract_companies']),
            signing_date=signing_date,
            signing_date_disp=zenhan(signing_date_disp),
            expiration_date=expiration_date,
            expiration_date_disp=zenhan(expiration_date_disp),
            auto_update=auto_update,
            file_name='',
            remarks='',
            # 非開示
            hidden_flag=hidden_flag,
            # 原本区分
            original_classification=request.POST['original_classification'],
            # 光通信Grpの債務保証有無
            loan_guarantee_availability=request.POST['loan_guarantee_availability'],
            # 稟議番号
            ringi_no=request.POST['ringi_no'],
            ringi_url='',
            # 書面番号
            document_number=request.POST['document_number'],
            # 原本保管場所
            original_storage_location=request.POST['original_storage_location'],

            deleted_flag=False,
            create_user=request.user.username,
            modify_user=request.user.username,
            partner_corporate_number=partner_corporate_number
        ).save()
        # ログ レコード追加
        info('record is inserted by user id[' + request.session['_auth_user_id'] + '].(' + json.dumps(request.POST,
                                                                                                    ensure_ascii=False) + ')')

        # 管轄社の処理

        # 管轄社番号
        # lc_list = request.POST.getlist('local_company')
        lc_list = request.POST['local_company_number'].split(",")
        if lc_list:
            for lc in lc_list:
                if lc:
                    rec = LocalCompany.objects.filter(id=int(lc))
                    if rec:
                        IndexLocalCompany(
                            index_id=Index.objects.latest('create_date').id,
                            local_company_id=int(lc),
                        ).save()

        # 結果表示
        indexes = Index.objects.filter(deleted_flag=False,
                                    id=Index.objects.latest('create_date').id)
        # スーパーユーザでなければ管轄社で表示を絞る
        # if not request.user.is_superuser:
        #     # 管轄社の処理
        #     lc_list = list()
        #     src_list = list()
        #     # 新形式 2019/05/21
        #     rlc = RestrictLocalCompany.objects.filter(user_id=request.user.id)
        #     if rlc:
        #         for r in rlc:
        #             src_list.append(r.local_company_id)
        #         for i in IndexLocalCompany.objects.filter(local_company_id__in=src_list):
        #             lc_list.append(i.index_id)
        #         indexes = indexes.filter(id__in=lc_list)
                # # print(len(indexes))

        # hidden_flagの処理
        if not request.user.has_perm('contract_index.view_hidden'):
            indexes = indexes.filter(hidden_flag=False)

        # 管轄社カラム用
        if request.user.has_perm('contract_index.read_localcompany'):
            indexes = indexes.prefetch_related('localcompanies')

        indexes = indexes.all()[:100]
        content = {
            'name': request.user,
            # 削除フラグは取得しない
            # 'indexes': Index.objects.all(),
            'old': {},
            'indexes': indexes,
            'indexes_localCompanies': IndexLocalCompany.objects.all(),
            'result': 'レコードを追加しました。',  # result,
            'original_classification_dict': original_classification_dict().items(),
            'original_storage_location_dict': original_storage_location_dict().items(),
        }
        #     # return redirect('contract_index:index')
        return render(request, 'contract_index/index.html', content)
    else:
        content = {
            'name': request.user,
            # 削除フラグは取得しない
            # 'indexes': Index.objects.all(),
            'indexes': [],
            'indexes_localCompanies': IndexLocalCompany.objects.all(),
            'localCompanies': LocalCompany.objects.all().order_by('local_company_name'),
            'result': None,
            'original_classification_dict': original_classification_dict().items(),
            'original_storage_location_dict': original_storage_location_dict().items(),
        }
        return render(request, 'contract_index/addrecord.html', content)


@login_required
def changerecord(request):
    info("changerecord")
    """
    レコード編集への遷移です。
    """
    target_list = request.POST.getlist('target_id_list')
    add_localcompany_number = request.POST['add_localcompany_number']
    delete_localcompany_number = request.POST['delete_localcompany_number']
    after_localcompany_number = request.POST['after_localcompany_number']
    company_name = request.POST.get('company_name', '')
    # 文字列の辞書化
    if 'post_dict' in request.POST:
        post_dict = ast.literal_eval(request.POST['post_dict'])
    else:
        post_dict = dict()
    if 'changerecord' in request.POST:
        indexes = Index.objects.filter(
            id=request.POST['changerecord']).prefetch_related('localcompanies')
    else:
        indexes = dict()
    if 'sort_order' in request.POST:
        sort_order = request.POST['sort_order']
    else:
        sort_order = ''
    if 'sort_key' in request.POST:
        sort_key = request.POST['sort_key']
    else:
        sort_key = ''

    # 会社情報JSON出力
    lc = LocalCompany.objects.all()
    company_names_json = serializers.serialize('json', lc)
    info("START edit")
    # info(company_names_json)

    content = {
        'post_dict': post_dict,
        'name': request.user,
        'indexes': indexes,
        'indexes_localCompanies': IndexLocalCompany.objects.all(),
        'change_record_id': request.POST['changerecord'],
        'sort_order': sort_order,
        'sort_key': sort_key,
        'add_localcompany_number': add_localcompany_number,
        'delete_localcompany_number': delete_localcompany_number,
        'after_localcompany_number': after_localcompany_number,
        'localcompanies': LocalCompany.objects.all().order_by('local_company_name'),
        'result': None,
        'original_classification_dict': original_classification_dict().items(),
        'original_storage_location_dict': original_storage_location_dict().items(),
        'company_names_json': company_names_json,
        'company_name': company_name,
    }
    return render(request, 'contract_index/changerecord.html', content)


@login_required
def local_company(request):
    info("local_company")
    """
    管轄社テーブル一覧への遷移です。
    """
    content = {
        'name': request.user,
        'localcompanies': LocalCompany.objects.all(),
        'result': None,
    }
    return render(request, 'contract_index/localcompany.html', content)


@login_required
def import_csv(request):
    """
    インポートへの遷移です。
    """
    content = {
        'name': request.user,
        'localcompanies': LocalCompany.objects.all(),
        'result': None,
    }
    return render(request, 'contract_index/import_csv.html', content)


# indexのデータ追加処理
@login_required
@transaction.atomic
def add_rec(request):
    info("add_rec")
    """
    レコード追加実行時の処理をする関数です。
    """

    # 日付の精査処理
    # 締結日
    signing_date = ''
    signing_date_disp = ''
    if request.POST['signing_date_y']:
        signing_date_disp += request.POST['signing_date_y']
        if request.POST['signing_date_m']:
            signing_date_disp += '-' + request.POST['signing_date_m']
            if request.POST['signing_date_d']:
                signing_date_disp += '-' + request.POST['signing_date_d']
                signing_date = signing_date_disp
            else:
                signing_date = signing_date = signing_date_disp + '-01'
        else:
            signing_date = signing_date_disp + '-01-01'
    else:
        signing_date_disp = ''
        signing_date = None

    # 有効期限
    expiration_date = None
    expiration_date_disp = ''

    auto_update = None

    # 非開示フラグ

    hidden_flag = 0
    pdf_path = ''
    if request.POST.get('hidden_flag') == 'true':
        hidden_flag = 1
    if request.POST.get('pdf_path'):
        pdf_path = request.POST['pdf_path']

    # 相手先法人番号
    number_array = request.POST['partner_corporate_number'].strip().split(",")
    modified_val = []
    for number_item in number_array:                            
        if not check_pc_number(number_item.strip()):
            content = {
                'name': request.user,
                'indexes': [],
                'indexes_localCompanies': [],
                'localCompanies': LocalCompany.objects.all().order_by('local_company_name'),
                'result': "相手先法人番号を正しく入力してください",
                'original_classification_dict': original_classification_dict().items(),
                'original_storage_location_dict': original_storage_location_dict().items(),
            }
            return render(request, 'contract_index/addrecord.html', content)
        modified_val.append(number_item.strip())
    partner_corporate_number = ",".join(modified_val)

    Index(
        pdf_path=pdf_path,
        contract_title=zenhan(request.POST['contract_title']),
        signing_target_kou='',
        signing_target_otsu='',
        contract_companies=zenhan(request.POST['contract_companies']),
        signing_date=signing_date,
        signing_date_disp=zenhan(signing_date_disp),
        expiration_date=expiration_date,
        expiration_date_disp=zenhan(expiration_date_disp),
        auto_update=auto_update,
        file_name='',
        remarks='',
        # 非開示
        hidden_flag=hidden_flag,
        # 原本区分
        original_classification=request.POST['original_classification'],
        # 光通信Grpの債務保証有無
        loan_guarantee_availability=request.POST['loan_guarantee_availability'],
        # 稟議番号
        ringi_no=request.POST['ringi_no'],
        ringi_url='',
        # 書面番号
        document_number=request.POST['document_number'],
        # 原本保管場所
        original_storage_location=request.POST['original_storage_location'],

        deleted_flag=False,
        create_user=request.user.username,
        modify_user=request.user.username,
        partner_corporate_number=partner_corporate_number
    ).save()
    # ログ レコード追加
    info('record is inserted by user id[' + request.session['_auth_user_id'] + '].(' + json.dumps(request.POST,
                                                                                                  ensure_ascii=False) + ')')

    # 管轄社の処理

    # 管轄社番号
    # lc_list = request.POST.getlist('local_company')
    lc_list = request.POST['local_company_number'].split(",")
    if lc_list:
        for lc in lc_list:
            if lc:
                rec = LocalCompany.objects.filter(id=int(lc))
                if rec:
                    IndexLocalCompany(
                        index_id=Index.objects.latest('create_date').id,
                        local_company_id=int(lc),
                    ).save()

    # 結果表示
    indexes = Index.objects.filter(deleted_flag=False,
                                   id=Index.objects.latest('create_date').id)
    # スーパーユーザでなければ管轄社で表示を絞る
    # if not request.user.is_superuser:
    #     # 管轄社の処理
    #     lc_list = list()
    #     src_list = list()
    #     # 新形式 2019/05/21
    #     rlc = RestrictLocalCompany.objects.filter(user_id=request.user.id)
    #     if rlc:
    #         for r in rlc:
    #             src_list.append(r.local_company_id)
    #         for i in IndexLocalCompany.objects.filter(local_company_id__in=src_list):
    #             lc_list.append(i.index_id)
    #         indexes = indexes.filter(id__in=lc_list)
            # # print(len(indexes))

    # hidden_flagの処理
    if not request.user.has_perm('contract_index.view_hidden'):
        indexes = indexes.filter(hidden_flag=False)

    # 管轄社カラム用
    if request.user.has_perm('contract_index.read_localcompany'):
        indexes = indexes.prefetch_related('localcompanies')

    indexes = indexes.all()[:100]
    content = {
        'name': request.user,
        # 削除フラグは取得しない
        # 'indexes': Index.objects.all(),
        'indexes': indexes,
        'indexes_localCompanies': IndexLocalCompany.objects.all(),
        'result': 'レコードを追加しました。',  # result,
        'original_classification_dict': original_classification_dict().items(),
        'original_storage_location_dict': original_storage_location_dict().items(),
    }
    #     # return redirect('contract_index:index')
    return render(request, 'contract_index/index.html', content)

       
# 検索機能 + 編集処理
@login_required
def searchresult(request):
    info("searchresult")
    """
    検索処理のための関数です。
    検索条件の再利用などのため
    編集（変更・削除）時もこちらの関数を使っています
    """
    # 直接アクセスされた場合403
    if not request.POST:
        return redirect('contract_index:search')
    result = ''
    change_id = ''

    # 会社情報JSON出力
    lc = LocalCompany.objects.all()
    company_names_json = serializers.serialize('json', lc)
    info("START searchResult")
    # info(company_names_json)
    # # print(ringi_json)
    # 削除する
    try:
        if request.POST['remove']:
            rec = Index.objects.filter(id=request.POST['change_id'])
            change_id = request.POST['change_id']
            # rec.delete()
            # 削除はデリートではなく、フラグで見えなくする
            for r in rec:
                r.deleted_flag = 1
                r.save()
            result = 'レコードを削除しました。'
            # ログ レコード削除
            info('record(ID=' + change_id + ') is deleted by user id[' + request.session[
                '_auth_user_id'] + '].(' + json.dumps(request.POST, ensure_ascii=False) + ')')
    except:
        pass

    # キャンセル
    try:
        if request.POST['cancel']:
            change_id = request.POST['change_id']
            result = 'キャンセルしました。'
    except:
        pass

    # 登録する
    try:
        if request.POST['edit']:
            info("EDIT")
            rec = Index.objects.filter(id=request.POST['change_id'])
            change_id = request.POST['change_id']
            info("change_id" + change_id)

            with transaction.atomic():
                for r in rec:
                    # 契約書名
                    if request.POST['change_contract_title']:
                        r.contract_title = request.POST['change_contract_title']
                    else:
                        raise ValueError('NotNullです')

                    # 会社名甲乙
                    r.signing_target_kou = ''
                    r.signing_target_otsu = ''

                    # 契約当事者
                    # info(request.POST['change_contract_companies'])
                    if request.POST['change_contract_companies'] != '':
                        r.contract_companies = request.POST['change_contract_companies']
                    else:
                        raise ValueError('NotNullです')
                    # 日付の精査処理
                    # 締結日
                    signing_date = ''
                    signing_date_disp = ''
                    if request.POST['change_signing_date_y']:
                        signing_date_disp += request.POST['change_signing_date_y']
                        if request.POST['change_signing_date_m']:
                            signing_date_disp += '-' + \
                                request.POST['change_signing_date_m']
                            if request.POST['change_signing_date_d']:
                                signing_date_disp += '-' + \
                                    request.POST['change_signing_date_d']
                                signing_date = signing_date_disp
                            else:
                                signing_date = signing_date_disp + '-01'
                        else:
                            signing_date = signing_date_disp + '-01-01'
                    else:
                        signing_date_disp = ''
                        signing_date = None
                    r.signing_date = signing_date
                    r.signing_date_disp = signing_date_disp

                    # 有効期限
                    expiration_date = None
                    expiration_date_disp = ''
                    r.expiration_date = expiration_date
                    r.expiration_date_disp = expiration_date_disp
                    # 自動更新
                    r.auto_update = None

                    # ファイル名
                    r.file_name = ''

                    # 備考
                    r.remarks = None

                    # 原本区分
                    if request.POST['change_original_classification'] != '':
                        r.original_classification = request.POST['change_original_classification']
                    else:
                        r.original_classification = None

                    # 契約終了フラグ
                    r.contract_termination_flag = False
                    if request.POST.get('change_contract_termination_flag') == 'true':
                        r.contract_termination_flag = True

                    # 光通信Grpの債務保証有無の登録
                    if request.POST['change_loan_guarantee_availability'] != '':
                        r.loan_guarantee_availability = request.POST['change_loan_guarantee_availability']
                    else:
                        r.loan_guarantee_availability = None

                    # 稟議番号
                    info("ringi_no:")
                    if request.POST['change_ringi_no'] != '':
                        # info(request.POST['change_ringi_no'])
                        r.ringi_no = request.POST['change_ringi_no']
                        # ringi_url = getRingiURL(request.POST['change_ringi_no'])
                        # r.ringi_url = ringi_url
                    else:
                        r.ringi_no = None
                        # r.ringi_url = ''
                    info("ringi_no:end:")

                    # 書面番号の登録
                    if request.POST['change_document_number'] != '':
                        r.document_number = request.POST['change_document_number']
                    else:
                        r.document_number = None

                    info("change_pdf_path")
                    if request.user.has_perm('contract_index.pdf_path'):
                        # 保管場所URL
                        if request.POST['change_pdf_path']:
                            r.pdf_path = request.POST['change_pdf_path']
                        else:
                            r.pdf_path = ''

                    info("change_hidden_flag")
                    if request.user.has_perm('contract_index.hidden_flag'):
                        # 非開示フラグ
                        r.hidden_flag = False
                        if request.POST.get('change_hidden_flag') == 'true':
                            r.hidden_flag = True

                    info("change_original_storage_location")
                    # 原本保管場所の登録
                    if request.POST['change_original_storage_location'] != '':
                        r.original_storage_location = request.POST.get(
                            'change_original_storage_location')
                    else:
                        r.original_storage_location = None

                    # 相手先法人番号の登録
                    if request.POST['change_partner_corporate_number'].strip() != '':
                        number_array = request.POST['change_partner_corporate_number'].strip().split(",")
                        modified_val = []
                        for number_item in number_array:                            
                            if not check_pc_number(number_item.strip()):
                                raise ValueError("partner_corporate_number")
                            modified_val.append(number_item.strip())
                        r.partner_corporate_number = ",".join(modified_val)
                        
                    r.modify_user = request.user.username
                    info("save:" + r.modify_user)
                    r.save()
                    info("save end:")

            # 管轄社の処理
            base = request.POST.get('base_localcompany_number')
            if base is not None:
                for v in base.split(","):
                    if not v:
                        continue
                    base = v
            add = request.POST['add_localcompany_number']
            # print("add", add)
            if add is not None:
                for v in add.split(","):
                    # info(v)
                    if not v:
                        continue
                    rec = LocalCompany.objects.filter(id=v)
                    if rec:
                        obj = IndexLocalCompany.objects.filter(
                            local_company_id=v, index_id=change_id)
                        if obj.first() is not None:
                            obj = IndexLocalCompany.objects.filter(
                                local_company_id=v, index_id=change_id).get()
                            b = IndexLocalCompany.objects.get(id=obj.id)
                            b.add_flg = 1
                            b.save()
                        else:
                            IndexLocalCompany(
                                index_id=int(change_id),
                                local_company_id=v,
                                add_flg=1,
                            ).save()

            delete = request.POST.get('delete_localcompany_number')
            # print("edit delete", delete)
            info("delete")

            if delete is not None:
                for v in delete.split(","):
                    if not v:
                        continue
                    rec = LocalCompany.objects.filter(id=v)
                    if rec:
                        obj = IndexLocalCompany.objects.filter(
                            local_company_id=v, index_id=change_id)
                        if obj.first() is not None:
                            obj = IndexLocalCompany.objects.filter(
                                local_company_id=v, index_id=change_id).get()
                            b = IndexLocalCompany.objects.get(id=obj.id)
                            info("flag_value")
                            # print("flag_value", b.add_flg)
                            info(b.add_flg)
                            if b.add_flg == 0:
                                b.add_flg = 2
                            elif b.add_flg == 1:
                                b.add_flg = 3
                            # print("after_flag_value", b.add_flg, b.id)
                            b.save()
                        else:
                            info("obj first NONW")
                            message += "■No:" + change_id + "[" + v + "]は登録されていないので除去できません"
                    else:
                        message += "[" + v + "]は法人番号マスターに存在しません"

            result = '更新完了しました。'
            # ログ:レコード 変更
            info('record(ID=' + change_id +
                 ') is updated by user id[' + request.session['_auth_user_id'] + ']')
    except ValueError as e:
        result = '入力に不備があり更新に失敗しました。'
    except:
        pass
    #     result = '不明の原因により更新に失敗しました。'

    # 一括反映を実行する
    try:
        if request.POST['confirmation']:
            info("BULK EDIT")
            message = ''
            # 反映対象
            target_list = request.POST.getlist('target_id_list')

            with transaction.atomic():
                for i_id in target_list:
                    after = request.POST.get(
                        'update[' + i_id + '][add_localcompany_number]')
                    info(after)
                    for v in after.split(","):
                        info("after")
                        if not v:
                            info("not" + v)
                            continue
                        info("is:" + v)
                        rec = LocalCompany.objects.filter(id=v)
                        info(rec)
                        if rec:
                            obj = IndexLocalCompany.objects.filter(
                                local_company_id=v, index_id=i_id)
                            if obj.first() is not None:
                                obj = IndexLocalCompany.objects.filter(
                                    local_company_id=v, index_id=i_id).get()
                                b = IndexLocalCompany.objects.get(id=obj.id)
                                b.add_flg = 1
                                b.save()
                            else:
                                IndexLocalCompany(
                                    index_id=int(i_id),
                                    local_company_id=v,
                                    add_flg=1,
                                ).save()
                        else:
                            message += "[" + v +"]は法人番号マスターに存在しません"
                        info("after end")
                    delete = request.POST.get(
                        'update[' + i_id + '][delete_localcompany_number]')
                    info(delete)
                    for v in delete.split(","):
                        info("delete")
                        if not v:
                            continue
                        info(v)
                        rec = LocalCompany.objects.filter(id=v)
                        if rec:
                            obj = IndexLocalCompany.objects.filter(
                                local_company_id=v, index_id=i_id)
                            if obj.first() is not None:
                                obj = IndexLocalCompany.objects.filter(
                                    local_company_id=v, index_id=i_id).get()
                                b = IndexLocalCompany.objects.get(id=obj.id)
                                info("flag_value")
                                # print("flag_value", b.add_flg)
                                info(b.add_flg)
                                if b.add_flg == 0:
                                    b.add_flg = 2
                                elif b.add_flg == 1:
                                    b.add_flg = 3
                                else:
                                    message += "■No:" + i_id + "[" + v +"]は登録されていないので除去できません"
                                    continue
                                # print("after_flag_value", b.add_flg, b.id)
                                b.save()
                            else:
                                info("obj first NONW")
                                message += "■No:" + i_id + "[" + v +"]は登録されていないので除去できません"
                        else:
                            message += "[" + v +"]は法人番号マスターに存在しません"

                info("ALL END")
                result = '一括反映を行いました。' + message
                # ログ:レコード 変更
                # info('companyNumber IKKATHU is updated by user id[' + request.session['_auth_user_id'] + '].(' + json.dumps(request.POST, ensure_ascii=False) + ')')
                info(
                    'companyNumber IKKATHU is updated by user id[' + request.session['_auth_user_id'] + ']')
    except:
        pass

    is_kouotsu_mutual_search = False

    order = dict()
    q_query = Q(pk__isnull=True)
    order_disp = dict()
    order_exclude = dict()
    order_exclude_disp = dict()
    number_of_search_words = 0

    indexes = Index.objects.all()

    if 'special_search' in request.POST:
        # 直近1000件検索
        if request.POST['special_search'] == 'last1000':
            indexes = indexes.order_by('-id')
            order_disp['特殊検索'] = '直近1000件'
        # 全件検索
        elif request.POST['special_search'] == 'all':
            indexes = indexes.order_by('-id')
            order_disp['特殊検索'] = '全件'
    else:
        # 1段目
        # 契約書名の検索
        post_dict = parser.parse(request.POST.urlencode())
        conditions = None
        if 'conditions' in post_dict:
            conditions = post_dict['conditions']
        index = 0

        # print(conditions)
        if conditions is not None:

            sub_queries = Q()
            temp_cc_pack = []
            temp_cn_pack = []

            for key, condition in conditions.items():

                if condition["where_type"] == "or":
                    sub_queries &= make_cc_query(temp_cc_pack)
                    sub_queries &= make_cn_query(temp_cn_pack)
                    q_query |= sub_queries
                    sub_queries = Q()
                    temp_cc_pack = []
                    temp_cn_pack = []

                search_condition = '('
                if index == 0:
                    search_condition += 'or)'
                else:
                    search_condition += condition['where_type'] + ')'

                
                if 'contract_title' in condition and condition['contract_title']:
                    
                    if 'contract_title_checkbox' in condition:
                        sub_queries &= Q(
                            contract_title__iexact = condition['contract_title'])

                        add_condition(order_disp, '契約書名(完全一致)',
                                      condition['contract_title'])

                    else:
                        sub_queries &= Q(contract_title__icontains = condition['contract_title'])

                        add_condition(order_disp, '契約書名', condition['contract_title'])

                if 'contract_title_exclude' in condition and condition['contract_title_exclude']:

                    sub_queries = ~Q(
                        contract_title__icontains=condition['contract_title_exclude'])

                    add_condition(order_exclude_disp, '契約書名',
                                  condition['contract_title_exclude'])

                # 契約当事者の検索
                if 'contract_companies' in condition and condition['contract_companies']:
                    
                    if 'contract_companies_checkbox' in condition:
                        temp_cc_pack.append({
                            "keyword": condition['contract_companies'],
                            "is_exact": True
                        })
                        add_condition(order_disp, '契約当事者(完全一致)',
                                      condition['contract_companies'])
                        sub_queries &= Q(
                            contract_companies__icontains = "/{}/".format(condition['contract_companies']))
                    else:
                        temp_cc_pack.append({
                            "keyword": condition['contract_companies'],
                            "is_exact": False
                        })

                        sub_queries &= Q(
                            contract_companies__icontains = condition['contract_companies'])

                        add_condition(order_disp, '契約当事者(部分一致)',
                                      condition['contract_companies'])


                # 契約書名の除外検索
                if 'contract_companies_exclude' in condition and condition['contract_companies_exclude']:
                    sub_queries = ~Q(contract_companies__icontains=condition['contract_companies_exclude'])

                    add_condition(order_exclude_disp, '契約当事者', condition['contract_companies_exclude']
                                  + search_condition)

                # 締結日の検索
                if 'signing_date_from' in condition and 'signing_date_to' in condition and (date_check(condition['signing_date_from']) or
                                                                                            date_check(condition['signing_date_to'])):
                    # 開始日に入力がなければ1900/1/1に設定
                    if date_check(condition['signing_date_from']):
                        start_list = condition['signing_date_from'].split('/')
                        start_disp = condition['signing_date_from'] + 'から'
                    else:
                        start_list = ['1900', '1', '1']
                        start_disp = '1900/1/1から'
                    # 終了日に入力がなければ本日に設定
                    if date_check(condition['signing_date_to']):
                        end_list = condition['signing_date_to'].split('/')
                        end_disp = condition['signing_date_to'] + 'まで'
                    else:

                        end_list = date.today().strftime('%Y/%m/%d').split('/')
                        end_disp = '本日まで'
                    start = date(int(start_list[0]), int(
                        start_list[1]), int(start_list[2]))
                    end = date(int(end_list[0]), int(
                        end_list[1]), int(end_list[2]))
                    # new_end = end + timedelta(days=1)
                    new_end = end

                    sub_queries &= Q(signing_date__range=[start, new_end])

                    add_condition(order_disp, '締結日', start_disp + end_disp)

                if 'ringi_no' in condition and condition['ringi_no']:
                    sub_queries &= Q(ringi_no__icontains = condition['ringi_no'])

                    add_condition(order_disp, '稟議番号', condition['ringi_no'])

                # 書面番号の検索
                if request.user.has_perm('contract_index.view_document_number'):
                    if 'document_number' in condition and condition['document_number']:

                        sub_queries &= Q(
                            document_number__iexact=condition['document_number'])

                        add_condition(order_disp, '書面番号',
                                      condition['document_number'])

                # 原本区分の検索
                if 'original_classification' in condition and condition['original_classification']:

                    sub_queries &= Q(
                        original_classification__icontains=condition['original_classification'])
                
                    # 条件表示の文字列作成
                    add_condition(order_disp, '原本区分',
                                  condition['original_classification'])

                if 'original_classification_exclude' in condition and condition['original_classification_exclude']:

                    sub_queries &= ~Q(
                        original_classification__icontains=condition['original_classification_exclude'])

                    # 条件表示の文字列作成
                    add_condition(order_exclude_disp, '原本区分',
                                  condition['original_classification_exclude'])

                # 終了フラグの検索
                if 'contract_termination_flag' in condition:
                    if condition['contract_termination_flag'] == 'true':

                        sub_queries &= Q(contract_termination_flag=1)
                        add_condition(order_disp, '終了フラグ', '終了')

                # 光通信Grpの債務保証有無の検索
                if request.user.has_perm('contract_index.view_loan_guarantee_availability'):
                    if 'loan_guarantee_availability' in condition and condition['loan_guarantee_availability']:

                        if 'loan_guarantee_availability_checkbox' in condition and condition['loan_guarantee_availability_checkbox'] == 'true':
                            sub_queries &= Q(loan_guarantee_availability__iexact = condition['loan_guarantee_availability'])
                            add_condition(order_disp, '光通信Grpの債務保証有無(完全一致)',
                                          condition['loan_guarantee_availability'] + search_condition)
                        else:
                            sub_queries &= Q(loan_guarantee_availability__icontains = condition['loan_guarantee_availability'])
                            add_condition(order_disp, '光通信Grpの債務保証有無', condition['loan_guarantee_availability'] + search_condition)


                    # 除外検索
                    if 'loan_guarantee_availability_exclude' in condition:
                        if condition['loan_guarantee_availability_exclude']:

                            sub_queries &= ~Q(loan_guarantee_availability__icontains = condition['loan_guarantee_availability_exclude'])

                            add_condition(order_exclude_disp, '光通信Grpの債務保証有無',
                                          condition['loan_guarantee_availability_exclude'] + search_condition)

                    # 空で検索
                    try:
                        if 'loan_guarantee_availability_check_blank' in condition and condition['loan_guarantee_availability_check_blank']:
                            order['loan_guarantee_availability__exact'] = ''
                            order_disp['光通信Grpの債務保証有無'] = '<<空>>'
                    except KeyError:
                        pass

                # pdf_path（保管場所URL）の検索
                if 'pdf_path' in condition:
                    if condition['pdf_path']:

                        if 'pdf_path_checkbox' in condition and condition['pdf_path_checkbox'] == 'true':
                            sub_queries &= Q(pdf_path__iexact = condition['pdf_path'])
                            add_condition(order_disp, 'URL(完全一致)', condition['pdf_path'])
                        else:
                            sub_queries &= Q(pdf_path__icontains = condition['pdf_path'])
                            add_condition(order_disp, 'URL', condition['pdf_path'])

                # 非開示の検索
                if 'hidden_flag' in condition:
                    if condition['hidden_flag'] == 'true':
                        sub_queries &= Q(hidden_flag=1)
                        order_disp['非開示'] = '非開示'

                # 原本保管場所の検索
                if request.user.has_perm('contract_index.view_original_storage_location'):
                    if 'original_storage_location' in condition:

                        if condition['original_storage_location'] == 'None':
                            pass
                        else:
                            sub_queries &= Q(original_storage_location__iexact = condition['original_storage_location'])
                            add_condition(order_disp, '原本保管場所',
                                          condition['original_storage_location'])

                    if 'original_storage_location_exclude' in condition:
                        if condition['original_storage_location_exclude'] == 'None':
                            pass
                        else:
                            sub_queries &= ~Q(original_storage_location = condition['original_storage_location_exclude'])
                            add_condition(
                                order_exclude_disp, '原本保管場所', condition['original_storage_location_exclude'])
                
                # 相手先法人番号
                if 'partner_corporate_number' in condition:
                    if condition['partner_corporate_number'] == 'None' or condition['partner_corporate_number'] == '':
                        pass
                    else:
                        cur_number = condition['partner_corporate_number']
                        sub_queries &= Q(partner_corporate_number__startswith = "{},".format(cur_number)) | Q(partner_corporate_number__icontains = ",{},".format(cur_number)) | Q(partner_corporate_number__endswith = ",{}".format(cur_number)) | Q(partner_corporate_number__iexact = cur_number)
                        add_condition(
                            order_disp, '相手先法人番号', condition['partner_corporate_number'])

                # 管轄社法人番号（元データ）の検索
                if 'local_company_number_original' in condition and condition['local_company_number_original']:
                    temp_cn_pack.append({
                        "keyword": condition['local_company_number_original'],
                        "add_flg": [0, 2]
                    })
                    # sub_queries &= Q(index__local_company_id = condition['local_company_number_original']) 
                    # sub_queries &= (Q(index__add_flg = 0) | Q(index__add_flg = 2))

                    add_condition(order_disp, '管轄社法人番号（元）', condition['local_company_number_original'] + search_condition)
                    

                # 管轄社法人番号（統合フィールド）の検索
                if 'local_company_number_total' in condition and condition['local_company_number_total']:
                    temp_cn_pack.append({
                        "keyword": condition['local_company_number_total'],
                        "add_flg": [0, 1]
                    })
                    # sub_queries &= Q(index__local_company_id = condition['local_company_number_total']) 
                    # sub_queries &= (Q(index__add_flg = 0) | Q(index__add_flg = 1))

                    add_condition(order_disp, '管轄社法人番号（統合）', condition['local_company_number_total'] + search_condition)

                # 管轄社法人番号（追加フィールド）の検索
                if 'local_company_number_add' in condition and condition['local_company_number_add']:
                    temp_cn_pack.append({
                        "keyword": condition['local_company_number_add'],
                        "add_flg": [3, 1]
                    })
                    # sub_queries &= Q(index__local_company_id = condition['local_company_number_add']) 
                    # sub_queries &= (Q(index__add_flg = 1) | Q(index__add_flg = 3))

                    add_condition(order_disp, '管轄社法人番号（追加）', condition['local_company_number_add'] + search_condition)

                # 管轄社法人番号（除去フィールド）の検索
                if 'local_company_number_delete' in condition and condition['local_company_number_delete']:
                    temp_cn_pack.append({
                        "keyword": condition['local_company_number_delete'],
                        "add_flg": [3, 2]
                    })
                    # sub_queries &= Q(index__local_company_id = condition['local_company_number_delete']) 
                    # sub_queries &= (Q(index__add_flg = 2) | Q(index__add_flg = 3))

                    add_condition(order_disp, '管轄社法人番号（除去）', condition['local_company_number_delete'] + search_condition)

                # 管轄社の検索
                if 'local_company' in condition and condition['local_company']:

                    local_comp_list = condition['local_company']
                    local_comp_result_list_disp = list()

                    if isinstance(local_comp_list, list):
                        for comp in local_comp_list:
                            for i in LocalCompany.objects.filter(id=comp):
                                local_comp_result_list_disp.append(
                                    i.local_company_name)
                        sub_queries &= Q(
                            index__local_company_id__in=local_comp_list)
                    else:
                        for i in LocalCompany.objects.filter(id=local_comp_list):
                            local_comp_result_list_disp.append(
                                i.local_company_name)
                        sub_queries &=  Q(
                            index__local_company_id=local_comp_list)

                    add_condition(order_disp, '管轄社',
                                  local_comp_result_list_disp)

                if 'local_company_exclude' in condition and condition['local_company_exclude']:

                    local_comp_list = condition['local_company_exclude']
                    local_comp_result_list_disp = list()
                    if isinstance(local_comp_list, list):
                        for comp in local_comp_list:
                            for i in LocalCompany.objects.filter(id=comp):
                                local_comp_result_list_disp.append(
                                    i.local_company_name)
                        sub_queries = ~Q(
                            index__local_company_id__in=local_comp_list)
                    else:
                        for i in LocalCompany.objects.filter(id=local_comp_list):
                            local_comp_result_list_disp.append(
                                i.local_company_name)
                        sub_queries = ~Q(
                            index__local_company_id=local_comp_list)

                    add_condition(order_exclude_disp, '管轄社',
                                  local_comp_result_list_disp)

                index += 1
        
            sub_queries &= make_cc_query(temp_cc_pack)
            sub_queries &= make_cn_query(temp_cn_pack)
            q_query |= sub_queries
            sub_queries = Q()
            temp_cc_pack = []
            temp_cn_pack = []

        else:
            content = {
                'name': request.user,
                'indexes': indexes.filter(id=change_id),
                'indexes_localCompanies': IndexLocalCompany.objects.all(),
                'result': result,
            }

            return render(request, 'contract_index/searchresult.html', content)

    # 入力がない場合
    if not order_disp:
        return redirect('contract_index:search')

    # hidden_flagの処理
    if not request.user.has_perm('contract_index.view_hidden'):
        indexes = indexes.filter(hidden_flag=False)

    # ソートオーダ設定
    sort_key = ''
    if 'sort_order' in request.POST:
        if request.POST['sort_order'] == 'asc':
            sort_order = 'asc'
        else:
            sort_key = '-'
            sort_order = 'desc'
    sort_key += request.POST['sort_key']
    sort_key_post = request.POST['sort_key']

    if 'special_search' in request.POST:
        pass
    else:
        indexes = indexes.filter(deleted_flag=False, **order).filter(q_query).exclude(**order_exclude).order_by(sort_key)

    
    # スーパーユーザでなければ管轄社で表示を絞る
    info("search:02")
    if not request.user.is_superuser:
        # 管轄社の処理
        lc_list = list()
        src_list = list()
        # 新形式 2019/05/21
        rlc = RestrictLocalCompany.objects.filter(user_id=request.user.id)
        if rlc:
            for r in rlc:
                src_list.append(r.local_company_id)

            indexes = indexes.filter(index__local_company_id__in=src_list)

    # SQL発行数をへらすために以下表示はテンプレート側に移行

    # 直近1000件検索処理
    if 'special_search' in request.POST:
        result += '条件:' + str(order_disp)
    else:
        if order_disp:
            result += '条件:' + str(order_disp)
        if order_exclude_disp:
            result += '除外:' + str(order_exclude_disp)

    # 管轄社カラム用
    if request.user.has_perm('contract_index.read_localcompany'):
        indexes = indexes.prefetch_related('localcompanies')

    # 除外ボタンの反映
    if 'excluded_id' in request.POST:
        excluded_id_list = [int(s)
                            for s in request.POST.getlist('excluded_id')]
        indexes = indexes.exclude(id__in=excluded_id_list)

    if 'special_search' in request.POST:
        # 直近1000件検索処理
        if request.POST['special_search'] == 'last1000':
            indexes = indexes.filter(deleted_flag=False)
            indexes = indexes.all()[:1000]
        # 全件検索
        elif request.POST['special_search'] == 'all':
            indexes = indexes.filter(deleted_flag=False)
            indexes = indexes.all()

    # 一般的にはCOUNT(*)は遅いが検証した結果count()のほうが速かった
    # count = indexes.aggregate(models.Count('id'))
    count = indexes.count()
    export_q = indexes
    # export_q = indexes.all()[:100]
    # indexes = indexes.all()[:int(request.POST['limit_num'])]
    # offsetとlimit
    all_page_num = math.ceil(count / 100)
    if 'off_set' in request.POST:
        off_set = int(request.POST['off_set']) * 100
        limit = off_set + 100
        indexes = indexes.all()[off_set:limit]
        start_rec = off_set + 1
        current_page_num = int(request.POST['off_set']) + 1
    else:
        indexes = indexes.all()[:100]
        start_rec = 1
        current_page_num = 1

    # 何件目まで表示しているか
    if start_rec + 99 - count > 0:
        end_rec = count
    else:
        end_rec = start_rec + 99
    # POSTの再送信
    if request.method == "POST":
        post_dict = dict(six.iterlists(request.POST))
        del post_dict['sort_order']
        del post_dict['sort_key']
        # 「一括反映」の実行対象指定で使用。この時点で処理済みになるため不要
        if request.POST.getlist('target_id_list'):
            del post_dict['target_id_list']

    indexes = indexes.prefetch_related('index')

    info("search: set content")
    content = {
        'all_page_num': all_page_num,
        'range_all_page_num': range(all_page_num),
        'range_page_btns': range(7),
        'current_page_num': current_page_num,
        'start_rec': start_rec,
        'end_rec': end_rec,
        'post_dict': post_dict,
        'count': count,
        'name': request.user,
        'indexes': indexes,
        'indexes_localCompanies': IndexLocalCompany.objects.all(),
        'result': result,
        'sort_order': sort_order,
        'sort_key': sort_key_post,
        'original_classification_dict': original_classification_dict().items(),
        'original_storage_location_dict': original_storage_location_dict().items(),
        'company_names_json': company_names_json,
    }
    # chage_id追加
    if change_id:
        content['change_id'] = int(change_id)

    # CSV全件出力-------------------------------------------------------------------
    # 左上の「エクスポートALL」をクリック
    if 'export_all' in request.POST:
        info("EXPORT ALL")
        # ログ:CSV全件出力
        info('csv of search result all records is exported by user id[' + request.session[
            '_auth_user_id'] + '].(' + json.dumps(request.POST, ensure_ascii=False) + ')')

        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="index_all_records.csv"'
        sio = io.StringIO()

        writer = csv.writer(sio)

        # if request.user.has_perm('contract_index.view_url'):
        #     writer.writerow(["契約書名", "会社名・甲", "会社名・乙", "締結日", "有効期限", "自動更新", "ファイル名", "URL", "備考", "No."])
        # else:
        #     writer.writerow(["契約書名", "会社名・甲", "会社名・乙", "締結日", "有効期限", "自動更新", "ファイル名", "備考", "No."])
        writer.writerow(
            ["契約書名", "契約当事者", "締結日", "原本区分", "契約終了フラグ", "光通信Grpの債務保証有無", "稟議番号", "書面番号", "保管場所URL", "原本保管場所", "管轄社名",
             "No"])

        a_list = list()
        for i in export_q:
            # 自動更新のTrueを変換
            # if i.auto_update:
            #     auto_update_sign = '○'
            # else:
            #     auto_update_sign = '-'
            auto_update_sign = '-'

            # 締結日のNone変換
            if i.signing_date_disp:
                signing_date_disp_sign = i.signing_date_disp
            else:
                signing_date_disp_sign = '-'

            # 有効期限のNone変換
            # if i.expiration_date_disp:
            #     expiration_date_disp_sign = i.expiration_date_disp
            # else:
            #     expiration_date_disp_sign = '-'
            expiration_date_disp_sign = '-'

            # 締結終了フラグ
            contract_termination = '-'
            if i.contract_termination_flag:
                contract_termination = '終了'

            # 原本区分の変換
            original_classification = ''
            # if i.original_classification == "1":
            #     original_classification = '紙'
            # if i.original_classification == "2":
            #     original_classification = 'データ（クラウドサイン）'
            # if i.original_classification == "3":
            #     original_classification = 'データ（電子認証）'
            for k, v in original_classification_dict().items():
                if k == i.original_classification:
                    original_classification = v

            # 保管場所URL
            if i.storage_location_url:
                storage_location_url = i.storage_location_url
            else:
                storage_location_url = ''

            # 原本保管場所
            original_storage_location = ''
            # if i.original_storage_location == "1":
            #     original_storage_location = '法務部'
            # if i.original_storage_location == "2":
            #     original_storage_location = 'データ保管'
            for k, v in original_storage_location_dict().items():
                if k == i.original_storage_location:
                    original_storage_location = v

            # 管轄社名
            info("companies name")
            name_localcompanies_list = list()
            for lc in i.localcompanies.all():
                result_count = IndexLocalCompany.objects.filter(add_flg__in=[0, 1], local_company=lc,
                                                                index=i.id).count()
                if (result_count > 0):
                    name_localcompanies_list.append(str(lc))
                    info("add:" + str(lc))
            integration_localcompanies_name = ','.join(
                name_localcompanies_list)

            # 稟議番号
            ringi_no = ''
            if i.ringi_no is not None:
                ringi_no = '\'' + i.ringi_no

            # if request.user.has_perm('contract_index.view_url'):
            #     writer.writerow([i.contract_title, i.signing_target_kou, i.signing_target_otsu, signing_date_disp_sign, expiration_date_disp_sign, \
            #         auto_update_sign, i.file_name, i.pdf_path, i.remarks, i.id])
            # else:
            #     writer.writerow([i.contract_title, i.signing_target_kou, i.signing_target_otsu, signing_date_disp_sign, expiration_date_disp_sign, \
            #         auto_update_sign, i.file_name, i.remarks, i.id])

            writer.writerow([i.contract_title, i.contract_companies, signing_date_disp_sign, original_classification,
                             contract_termination,
                             i.loan_guarantee_availability, ringi_no, i.document_number, storage_location_url,
                             original_storage_location, integration_localcompanies_name, i.id])

        # return HttpResponse(a_list)

        # クエリリストの削除
        db.reset_queries()
        # エクセル用にエンコード
        response.write(sio.getvalue().encode('utf-8-sig'))
        del sio
        del writer
        return response
    # CSV全件出力-------------------------------------------------------------------
    # 更新用エクスポート
    if 'export_all4update' in request.POST:
        # ログ:CSV全件出力
        info('csv of search result all records is exported by user id[' + request.session[
            '_auth_user_id'] + '].(' + json.dumps(request.POST, ensure_ascii=False) + ')')

        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="index_all_records.csv"'
        sio = io.StringIO()

        writer = csv.writer(sio)

        # writer.writerow(["契約書名", "会社名・甲", "会社名・乙", "締結日", "有効期限", "自動更新", "ファイル名", "URL", "備考", "No.", "非表示", "管轄社"])
        writer.writerow(["契約書名", "契約当事者", "締結日", "原本区分", "契約終了フラグ", "光通信Grpの債務保証有無", "稟議番号", "書面番号", "保管場所URL", "管轄社名",
                         "管轄社法人番号（元）", "追加管轄社法人番号", "除外管轄社法人番号", "管轄社法人番号（統合）", "相手方法人番号", "原本保管場所", "No."])

        a_list = list()
        for i in export_q:
            # 自動更新のTrueを変換
            if i.auto_update:
                auto_update_sign = '○'
            else:
                auto_update_sign = '-'
            # 締結日のNone変換
            if i.signing_date_disp:
                signing_date_disp_sign = i.signing_date_disp
            else:
                signing_date_disp_sign = '-'

            # 有効期限のNone変換
            # if i.expiration_date_disp:
            #     expiration_date_disp_sign = i.expiration_date_disp
            # else:
            #     expiration_date_disp_sign = '-'
            expiration_date_disp_sign = '-'

            # 締結終了フラグ
            contract_termination = '-'
            if i.contract_termination_flag:
                contract_termination = '終了'

            # 非表示の変換
            # if i.hidden_flag:
            #     hidden_flag = '○'
            # else:
            #     hidden_flag = '-'
            hidden_flag = '-'

            # 管轄社名
            info("companies name")
            name_localcompanies_list = list()
            for lc in i.localcompanies.all():
                result_count = IndexLocalCompany.objects.filter(add_flg__in=[0, 1], local_company=lc,
                                                                index=i.id).count()
                if (result_count > 0):
                    name_localcompanies_list.append(str(lc))
                    info("add:" + str(lc))
            integration_localcompanies_name = ','.join(
                name_localcompanies_list)

            # 管轄社番号（元）
            info("companies base")
            base_localcompanies_list = list()
            for lc in i.localcompanies.all():
                result_count = IndexLocalCompany.objects.filter(add_flg__in=[0, 2], local_company=lc,
                                                                index=i.id).count()
                if (result_count > 0):
                    base_localcompanies_list.append(lc.id)
                    info("add:" + lc.id)
            base_localcompanies_number = ','.join(base_localcompanies_list)

            # 追加管轄社法人番号
            info("companies add")
            additional_localcompanies_list = list()
            for lc in i.localcompanies.all():
                result_count = IndexLocalCompany.objects.filter(
                    add_flg=1, local_company=lc, index=i.id).count()
                if (result_count > 0):
                    info("add:" + lc.id)
                    additional_localcompanies_list.append(lc.id)

            additional_localcompanies_number = ','.join(additional_localcompanies_list)

            # 除外管轄社法人番号
            info("companies delete")
            exclusion_localcompanies_list = list()
            for lc in i.localcompanies.all():
                result_count = IndexLocalCompany.objects.filter(
                    add_flg=2, local_company=lc, index=i.id).count()
                if (result_count > 0):
                    info("add:" + lc.id)
                    exclusion_localcompanies_list.append(lc.id)

            exclusion_localcompanies_number = ','.join(exclusion_localcompanies_list)

            info("companies total")
            # 管轄社番号（統合）
            integration_localcompanies_list = list()
            for lc in i.localcompanies.all():
                result_count = IndexLocalCompany.objects.filter(add_flg__in=[0, 1], local_company=lc,
                                                                index=i.id).count()
                if (result_count > 0):
                    info("add:" + lc.id)
                    integration_localcompanies_list.append(lc.id)
                # 再検索
                # for v in IndexLocalCompany.objects.filter(local_company=lc, index=i.id):
                #     if v.add_flg==2:
                #         integration_localcompanies_list.append(str(lc.id))
            integration_localcompanies_list = ','.join(integration_localcompanies_list)

            # 原本区分の変換
            original_classification = ''
            # if i.original_classification == "1":
            #     original_classification = '紙'
            # if i.original_classification == "2":
            #     original_classification = 'データ（クラウドサイン）'
            # if i.original_classification == "3":
            #     original_classification = 'データ（電子認証）'
            for k, v in original_classification_dict().items():
                if k == i.original_classification:
                    original_classification = v

            # 原本保管場所
            original_storage_location = ''
            # if i.original_storage_location == "1":
            #     original_storage_location = '法務部'
            # if i.original_storage_location == "2":
            #     original_storage_location = 'データ保管'
            for k, v in original_storage_location_dict().items():
                if k == i.original_storage_location:
                    original_storage_location = v

            # 稟議番号
            ringi_no = ''
            if i.ringi_no is not None:
                ringi_no = '\'' + i.ringi_no

            # 相手方法人番号
            partner_corporate_number = "" if i.partner_corporate_number is None else i.partner_corporate_number

            # writer.writerow([i.contract_title, i.signing_target_kou, i.signing_target_otsu, signing_date_disp_sign, expiration_date_disp_sign, \
            #     auto_update_sign, i.file_name, i.pdf_path, i.remarks, i.id, hidden_flag, localcompanies])
            info("writer")
            writer.writerow([i.contract_title, i.contract_companies, signing_date_disp_sign, original_classification,
                             contract_termination,
                             i.loan_guarantee_availability, ringi_no, i.document_number, i.storage_location_url,
                             integration_localcompanies_name, base_localcompanies_number,
                             additional_localcompanies_number, exclusion_localcompanies_number,
                             integration_localcompanies_list, partner_corporate_number, 
                             original_storage_location, i.id])

        # return HttpResponse(a_list)

        # クエリリストの削除
        db.reset_queries()
        # エクセル用にエンコード
        response.write(sio.getvalue().encode('utf-8-sig'))
        del sio
        del writer
        return response
    # クエリリストの削除
    info("delete query list")
    db.reset_queries()
    # ログ:検索
    # info('dbs are searched by user id[' + request.session['_auth_user_id'] + '].(' + content['result'] + ')')
    # info('dbs are searched by user id[' + request.session['_auth_user_id'] + '].(' + json.dumps(request.POST, ensure_ascii=False) + ')')
    return render(request, 'contract_index/searchresult.html', content)
    # except :
    #     return redirect('contract_index:search')


# csvアップロードとインポート機能
@login_required
def upload(request):
    info('デバッグ用:csv新規インポート1')
    """
    csvアップロード処理のための関数です。
    """
    inserted_records = 0
    first_id_inserted_now = 0
    result = ''
    if request.FILES:
        info('デバッグ用:csv新規インポート2')

        line_first = request.FILES['uploaded_csv'].readline()
        is_with_bom = line_first.startswith(b'\xEF\xBB\xBf')
        encoding = 'utf-8-sig' if is_with_bom else 'CP932'
        form_data = TextIOWrapper(
            request.FILES['uploaded_csv'], encoding=encoding)
        csv_file = csv.reader(form_data)
        is_header_row = True
        line_num = 0

        view_id_list = list()
        for line in csv_file:

            info('デバッグ用:csv新規インポート3')
            # 見出し行チェック
            # if is_header_row:
            #     # CSVファイルの判定 新規は12列
            #     if len(line) != 12:
            #         info("FORMAT ERROR")
            #         content = {
            #             'name': request.user,
            #             'result': 'CSVの形式に間違いがあるようです。再確認してください。(更新用や通常エクスポートのCSVを使っていませんか？)'
            #         }
            #         return render(request, 'contract_index/index.html', content)
            #     is_header_row = False
            #     # 見出し行はcontinueする
            #     continue
            # 全てのセルにデータがなければbreakする
            if not (line[0] or line[1] or line[2] or line[3] or line[4] or line[5]
                    or line[6] or line[7] or line[8] or line[9] or line[10]):
                continue

            # ######## v2 ########
            #  [0]契約書名,
            #  [1]会社名・甲,
            #  [2]会社名・乙,
            #  [3]締結日,
            #  [4]有効期限,
            #  [5]自動更新,
            #  [6]ファイル名,
            #  [7]URL,
            #  [8]備考,
            #  [9]非表示,
            # [10]管轄社
            # ######## v3 ########
            #  [0]契約書名,
            #  [1]契約当事者,
            #  [2]締結日,
            #  [3]原本区分,
            #  [4]契約終了フラグ,
            #  [5]光通信Grpの債務保証有無,
            #  [6]稟議番号,
            #  [7]書面番号,
            #  [8]PDF PATH
            #  [9]管轄社名,
            #  [10]管轄社法人番号,
            #  [11]原本保管場所

            IDX_CONTRACT_TITLE = 0
            IDX_CONTRACT_COMPANIES = 1
            IDX_SIGNING_DATE = 2
            IDX_ORIGINAL_CLASSIFICATION = 3
            IDX_CONTRACT_TERMINATION_FLAG = 4
            IDX_LOAN_GUARANTEE_AVAILABILITY = 5
            IDX_RINGI_NO = 6
            IDX_DOCUMENT_NUMBER = 7
            IDX_PDF_PATH = 8
            IDX_COMPANY_NUMBER = 10
            IDX_PARTNER_CORPORATE_NUMBER = 11
            IDX_ORIGINAL_STORAGE_LOCATION = 12

            info("LOAN:" + line[IDX_LOAN_GUARANTEE_AVAILABILITY])
            # フォーマットがおかしい場合
            # 契約書名：入力必須
            if not line[IDX_CONTRACT_TITLE]:
                content = {
                    'name': request.user,
                    'indexes': Index.objects.filter(id__in=view_id_list),
                    # 'indexes': None,
                    'indexes_localCompanies': IndexLocalCompany.objects.all(),
                    'original_classification_dict': original_classification_dict().items(),
                    'original_storage_location_dict': original_storage_location_dict().items(),
                    'result': '契約書名は入力必須です。ご確認お願い致します。'
                }
                return render(request, 'contract_index/index.html', content)

            # 契約当事者：入力必須
            if not line[IDX_CONTRACT_COMPANIES]:
                info(line[IDX_CONTRACT_COMPANIES])
                content = {
                    'name': request.user,
                    'indexes': Index.objects.filter(id__in=view_id_list),
                    # 'indexes': None,
                    'indexes_localCompanies': IndexLocalCompany.objects.all(),
                    'original_classification_dict': original_classification_dict().items(),
                    'original_storage_location_dict': original_storage_location_dict().items(),
                    'result': '契約当事者は入力必須です。ご確認お願い致します。'
                }
                return render(request, 'contract_index/index.html', content)

            # 原本保管場所：入力値の限定
            if line[IDX_ORIGINAL_STORAGE_LOCATION]:
                is_chack = False
                for k, v in original_storage_location_dict().items():
                    if v == line[IDX_ORIGINAL_STORAGE_LOCATION]:
                        is_chack = True
                        pass
                if not is_chack:
                    content = {
                        'indexes': Index.objects.filter(id__in=view_id_list),
                        'indexes_localCompanies': IndexLocalCompany.objects.all(),
                        'original_classification_dict': original_classification_dict().items(),
                        'original_storage_location_dict': original_storage_location_dict().items(),
                        'result': '原本保管場所は「法務部」「データ保管」「人事管理（出向系）」のいずれかを設定してください'
                    }
                    return render(request, 'contract_index/index.html', content)

            # # 非開示フラグ
            # if line[9].isdecimal():
            #     content = {
            #         'name': request.user,
            #         # 削除フラグは取得しない
            #         # 'indexes': Index.objects.all(),
            #         'indexes': None,
            #         'indexes_localCompanies': IndexLocalCompany.objects.all(),
            #         'result': 'CSVファイルのフォーマットが正しくないようです。ご確認お願い致します。'
            #     }
            #     return render(request, 'contract_index/index.html', content)

            info("Check companiy number")
            # 会社法人番号の有無
            if line[IDX_COMPANY_NUMBER]:
                for input_lc in line[IDX_COMPANY_NUMBER].split(','):
                    info(str(input_lc))
                    info("=============")
                    if not LocalCompany.objects.filter(id=input_lc):
                        content = {
                            'indexes': Index.objects.filter(id__in=view_id_list),
                            'indexes_localCompanies': IndexLocalCompany.objects.all(),
                            'original_classification_dict': original_classification_dict().items(),
                            'original_storage_location_dict': original_storage_location_dict().items(),
                            'result': '会社法人番号' + input_lc + 'はマスター情報に登録されていません'
                        }
                        return render(request, 'contract_index/index.html', content)

            info("Check partner corporate nubmer")
            # 相手方法人番号の有無
            if line[IDX_PARTNER_CORPORATE_NUMBER].strip():
                for input_lc in line[IDX_PARTNER_CORPORATE_NUMBER].strip().split(','):
                    if not check_pc_number(input_lc.strip()):
                        content = {
                            'indexes': Index.objects.filter(id__in=view_id_list),
                            'indexes_localCompanies': IndexLocalCompany.objects.all(),
                            'original_classification_dict': original_classification_dict().items(),
                            'original_storage_location_dict': original_storage_location_dict().items(),
                            'result': '相手方法人番号は半角英数字13桁のカンマ区切りで入力してください'
                        }
                        return render(request, 'contract_index/index.html', content)

            with transaction.atomic():
                # 日付の精査処理
                # 締結日
                if line[IDX_SIGNING_DATE] and line[IDX_SIGNING_DATE] != '-':
                    signing_date = date_scrutinizer(line[IDX_SIGNING_DATE])
                    signing_date_disp = zenhan(line[IDX_SIGNING_DATE])
                else:
                    signing_date = None
                    signing_date_disp = ''

                # # 有効期限
                expiration_date = None
                expiration_date_disp = ''
                # if line[4] and line[4] != '-':
                #     expiration_date = date_scrutinizer(line[4])
                #     expiration_date_disp = zenhan(line[4])
                # else:
                #     expiration_date = None
                #     expiration_date_disp = ''

                # # 自動更新の精査処理
                auto_update = None
                # if line[5] in ['×', 'X', '0', '無',]:
                #     auto_update = False
                # elif line[5] in ['○', '◎', '◯', '1', '有']:
                #     auto_update = True
                # else:
                #     auto_update = None

                # # ファイル名の精査処理
                file_name = None
                # if line[6]:
                #     file_name = line[6]
                # else:
                #     file_name = None

                # # 備考の精査処理
                remarks = None
                # if line[8]:
                #     remarks = line[8]
                # else:
                #     remarks = None

                # # pdf_pathの精査処理
                pdf_path = ''
                # if line[7]:
                #     pdf_path = line[7]
                # else:
                #     pdf_path = ''

                # # 非表示フラグの精査処理
                hidden_flag = False
                # if line[4] in ['○', '◎', '◯', '1', '有']:
                #     hidden_flag = True
                # else:
                #     hidden_flag = False

                # 契約終了フラグの精査処理
                if line[IDX_CONTRACT_TERMINATION_FLAG] in ['○', '◎', '◯', '1', '有', '終了']:
                    contract_termination_flag = True
                else:
                    contract_termination_flag = False

                # 稟議番号
                ringi_no = None
                if len(line[IDX_RINGI_NO].replace("'", '')) > 5:
                    ringi_no = line[IDX_RINGI_NO].replace("'", '')
                    info("ringi_no:" + ringi_no)

                # 原本区分の精査
                original_classification = line[IDX_ORIGINAL_CLASSIFICATION]

                # 原本保管場所の精査
                original_storage_location = None
                # if line[10] == "法務部":
                #     original_storage_location = "1"
                # if line[10] == "データ保管":
                #     original_storage_location = '2'
                for k, v in original_storage_location_dict().items():
                    if v == line[IDX_ORIGINAL_STORAGE_LOCATION]:
                        original_storage_location = k

                # 保管場所URL
                storage_location_url = line[IDX_PDF_PATH]

                # 相手方法人番号
                partner_corporate_number = line[IDX_PARTNER_CORPORATE_NUMBER].strip() if line[IDX_PARTNER_CORPORATE_NUMBER].strip() else None

                new_index = Index.objects.create(
                    pdf_path = storage_location_url,
                    contract_title = zenhan(line[IDX_CONTRACT_TITLE]),
                    signing_target_kou = '',
                    signing_target_otsu = '',
                    contract_companies = zenhan(line[IDX_CONTRACT_COMPANIES]),
                    signing_date = signing_date,
                    signing_date_disp = signing_date_disp,
                    expiration_date = expiration_date,
                    expiration_date_disp = expiration_date_disp,
                    auto_update = auto_update,
                    file_name = zenhan(file_name),
                    remarks = remarks,
                    hidden_flag = hidden_flag,
                    contract_termination_flag = contract_termination_flag,
                    deleted_flag = False,
                    create_user = request.user.username,
                    modify_user = request.user.username,
                    original_classification = original_classification,
                    loan_guarantee_availability = line[IDX_LOAN_GUARANTEE_AVAILABILITY],
                    ringi_no = ringi_no,
                    ringi_url = '',
                    document_number = line[IDX_DOCUMENT_NUMBER],
                    # line[8]
                    # line[9]
                    original_storage_location=original_storage_location,
                    partner_corporate_number = partner_corporate_number
                )
                inserted_records += 1
                view_id_list.append(new_index.id)
                info('デバッグ用:csv新規インポート4')

                # 管轄社名の処理
                # tmp = []
                # if line[8]:
                #     for lc in LocalCompany.objects.all():
                #         for input_lc in line[8].split(','):
                #             if lc.local_company_name == input_lc:
                #                 # 今回のインポートでの最初のIDを保存する
                #                 if first_id_inserted_now == 0:
                #                     first_id_inserted_now = Index.objects.latest('create_date').id
                #                 IndexLocalCompany(
                #                     index_id=Index.objects.latest('create_date').id,
                #                     local_company_id=lc.id,
                #                 ).save()
                #                 tmp.append(lc.id)
                # 管轄社IDの処理
                if line[IDX_COMPANY_NUMBER]:
                    for input_lc in line[IDX_COMPANY_NUMBER].split(','):
                        info(input_lc)
                        IndexLocalCompany.objects.create(
                            index_id=new_index.id,
                            local_company_id=input_lc,
                        )
                info('INSERT local_company_id')

                # for lc in LocalCompany.objects.all():
                #     for input_lc in line[IDX_COMPANY_NUMBER].split(','):
                #         if lc.id == int(input_lc):
                #             if int(input_lc) in tmp:
                #                 continue
                # 今回のインポートでの最初のIDを保存する
                # if first_id_inserted_now == 0:
                #     first_id_inserted_now = Index.objects.latest('create_date').id
                # info(Index.objects.latest('create_date').id)
                # IndexLocalCompany(
                #     index_id=Index.objects.latest('create_date').id,
                #     local_company_id=lc.id,
                # ).save()

                # 管轄社がない場合の処置
                if first_id_inserted_now == 0:
                    first_id_inserted_now = new_index.id
                line_num += 1  # ?

        # ログ:CSVインポート
        info(str(inserted_records) + ' record(s) is(are) inserted with csv by user id[' + request.session[
            '_auth_user_id'] + '].(' + json.dumps(request.POST, ensure_ascii=False) + ')')
        result += str(inserted_records) + '件のインポートを実行しました。'
    else:
        result += 'インポートをキャンセルしました。'

    # 今回挿入分のみにする
    indexes = Index.objects.filter(id__gte=first_id_inserted_now)
    indexes = indexes.filter(deleted_flag=False)

    # スーパーユーザでなければ管轄社で表示を絞る
    if not request.user.is_superuser:
        if not request.user.is_staff:
            # 管轄社の処理
            lc_list = list()
            src_list = list()
            # 新形式 2019/05/21
            rlc = RestrictLocalCompany.objects.filter(user_id=request.user.id)
            if rlc:
                for r in rlc:
                    src_list.append(r.local_company_id)
                # # LC1
                # if request.user.has_perm('contract_index.access_lc1'):
                #     src_list.append(1)
                # # LC2
                # if request.user.has_perm('contract_index.access_lc2'):
                #     src_list.append(2)
                # # LC3
                # if request.user.has_perm('contract_index.access_lc3'):
                #     src_list.append(3)
                # # LC4
                # if request.user.has_perm('contract_index.access_lc4'):
                #     src_list.append(4)
                # # LC5
                # if request.user.has_perm('contract_index.access_lc5'):
                #     src_list.append(5)
                # # LC6
                # if request.user.has_perm('contract_index.access_lc6'):
                #     src_list.append(6)
                for i in IndexLocalCompany.objects.filter(local_company_id__in=src_list):
                    lc_list.append(i.index_id)
                indexes = indexes.filter(id__in=lc_list)

    # hidden_flagの処理
    if not request.user.has_perm('contract_index.view_hidden'):
        indexes = indexes.filter(hidden_flag=False)

    # 管轄社カラム用
    if request.user.has_perm('contract_index.read_localcompany'):
        indexes = indexes.prefetch_related('localcompanies')

    content = {
        'name': request.user,
        # 削除フラグは取得しない
        # 'indexes': Index.objects.all(),
        'indexes': indexes,
        'indexes_localCompanies': IndexLocalCompany.objects.all(),
        'result': result,
        'original_classification_dict': original_classification_dict().items(),
        'original_storage_location_dict': original_storage_location_dict().items(),
    }
    return render(request, 'contract_index/index.html', content)


# 更新用csvアップロードとインポート機能
@login_required
@transaction.atomic
def upload2(request):
    info('debug UPDATE IMPORT')
    """
    更新用csvアップロード処理のための関数です。
    """
    uploaded_rec_list = list()
    inserted_records = 0
    first_id_inserted_now = 0
    result = ''
    if request.FILES:
        info('debug import 1')
        line_first = request.FILES['uploaded_csv'].readline()
        is_with_bom = line_first.startswith(b'\xEF\xBB\xBf')
        encoding = 'utf-8-sig' if is_with_bom else 'CP932'
        form_data = TextIOWrapper(
            request.FILES['uploaded_csv'], encoding=encoding)
        csv_file = csv.reader(form_data)
        is_header_row = True
        line_num = 0

        view_id_list = list()

        for line in csv_file:
            # 見出し行チェック
            if is_header_row:
                # CSVファイルの判定 更新は12列
                # info(len(line))
                if len(line) != 17:
                    content = {
                        'name': request.user,
                        'result': 'CSVの形式に間違いがあるようです。再確認してください。(新規用や通常エクスポートのCSVを使っていませんか？)'
                    }
                    return render(request, 'contract_index/index.html', content)
                is_header_row = False
                # 見出し行はcontinueする
                info("HEADER:" + line[15])

            # 全てのセルにデータがなければbreakする

            # ######## v3 ########
            #  [0]契約書名,
            #  [1]契約当事者,
            #  [2]締結日,
            #  [3]原本区分,
            #  [4]契約終了フラグ,
            #  [5]光通信Grpの債務保証有無,
            #  [6]稟議番号,
            #  [7]書面番号,
            #  [8]保管場所URL,
            #  [9]管轄社名（使わない）,
            #  [10]管轄社法人番号,
            # [11]追加管轄社法人番号,
            # [12]除外管轄社法人番号,
            # [13]統合管轄社法人番号（使わない）,
            # [14]原本保管場所
            # [15]No.
            IDX_CONTRACT_TITLE = 0
            IDX_CONTRACT_COMPANIES = 1
            IDX_SIGNING_DATE = 2
            IDX_ORIGINAL_CLASSIFICATION = 3
            IDX_CONTRACT_TERMINATION_FLAG = 4
            IDX_LOAN_GUARANTEE_AVAILABILITY = 5
            IDX_RINGI_NO = 6
            IDX_DOCUMENT_NUMBER = 7
            IDX_PDF_PATH = 8
            IDX_BASE_LOCALCOMPANIES_NUMBER = 10
            IDX_ADDITIONAL_LOCALCOMPANIES_NUMBER = 11
            IDX_EXCLUSION_LOCALCOMPANIES_NUMBER = 12
            IDX_PARTNER_CORPORATE_NUMBER = 14
            IDX_ORIGINAL_STORAGE_LOCATION = 15
            IDX_NO = 16

            info("TARGET:" + line[IDX_NO])
            if not (line[IDX_CONTRACT_TITLE] or line[IDX_CONTRACT_COMPANIES] or line[IDX_SIGNING_DATE]
                    or line[IDX_RINGI_NO] or line[6] or line[IDX_DOCUMENT_NUMBER] or line[IDX_PDF_PATH] or line[
                        IDX_BASE_LOCALCOMPANIES_NUMBER] or line[IDX_ORIGINAL_STORAGE_LOCATION] or line[IDX_NO]):
                info("continue:" + line[IDX_NO])
                continue

            # フォーマットがおかしい場合
            # 契約書名：入力必須
            if not line[IDX_CONTRACT_TITLE]:
                content = {
                    'indexes': Index.objects.filter(id__in=view_id_list),
                    'indexes_localCompanies': IndexLocalCompany.objects.all(),
                    'original_classification_dict': original_classification_dict().items(),
                    'original_storage_location_dict': original_storage_location_dict().items(),
                    'result': '契約書名は入力必須です。ご確認お願い致します。'
                }
                return render(request, 'contract_index/index.html', content)

            info(line[1])
            # 契約当事者：入力必須
            if not line[IDX_CONTRACT_COMPANIES]:
                content = {
                    'indexes': Index.objects.filter(id__in=view_id_list),
                    'indexes_localCompanies': IndexLocalCompany.objects.all(),
                    'original_classification_dict': original_classification_dict().items(),
                    'original_storage_location_dict': original_storage_location_dict().items(),
                    'result': '契約当事者は入力必須です。ご確認お願い致します。'
                }
                return render(request, 'contract_index/index.html', content)

            info("Check partner corporate nubmer")
            # 相手方法人番号の有無
            if line[IDX_PARTNER_CORPORATE_NUMBER].strip():
                for input_lc in line[IDX_PARTNER_CORPORATE_NUMBER].strip().split(','):
                    if not check_pc_number(input_lc.strip()):
                        content = {
                            'indexes': Index.objects.filter(id__in=view_id_list),
                            'indexes_localCompanies': IndexLocalCompany.objects.all(),
                            'original_classification_dict': original_classification_dict().items(),
                            'original_storage_location_dict': original_storage_location_dict().items(),
                            'result': '相手方法人番号は半角英数字13桁のカンマ区切りで入力してください'
                        }
                        return render(request, 'contract_index/index.html', content)

            # 日付の精査処理
            # 締結日
            if line[IDX_SIGNING_DATE] == '-':
                signing_date = None
                signing_date_disp = ''
            else:
                signing_date = date_scrutinizer(line[IDX_SIGNING_DATE])
                signing_date_disp = zenhan(line[IDX_SIGNING_DATE])

            # 有効期限
            expiration_date = None
            expiration_date_disp = ''

            # 自動更新の精査処理
            auto_update = 0
            # if line[5] in ['×', 'X', '0', '無',]:
            #     auto_update = False
            # elif line[5] in ['○', '◎', '◯', '1', '有']:
            #     auto_update = True
            # else:
            #     auto_update = None

            # ファイル名の精査処理
            file_name = None
            # if line[6]:
            #     file_name = line[6]
            # else:
            #     file_name = None

            # 備考の精査処理
            remarks = None
            # if line[8]:
            #     remarks = line[8]
            # else:
            #     remarks = None

            # 非表示フラグの精査処理
            hidden_flag = False

            # Noの精査処理
            rec = Index.objects.filter(id=line[IDX_NO])
            if not rec:
                content1 = {
                    'name': request.user,
                    # 削除フラグは取得しない
                    # 'indexes': Index.objects.all(),
                    'indexes': None,
                    'indexes_localCompanies': IndexLocalCompany.objects.all(),
                    'result': '存在しないNo.が含まれているようです。ご確認お願い致します。',
                    'original_classification_dict': original_classification_dict().items(),
                    'original_storage_location_dict': original_storage_location_dict().items(),
                }
                return render(request, 'contract_index/index.html', content1)
            uploaded_rec_list.append(line[IDX_NO])
            inserted_records += 1

            # 契約終了フラグの精査処理
            contract_termination_flag = 0
            if line[IDX_CONTRACT_TERMINATION_FLAG] in ['○', '◎', '◯', '1', '有', '終了']:
                contract_termination_flag = 1

            # 原本区分の精査
            original_classification = line[IDX_ORIGINAL_CLASSIFICATION]

            # 原本保管場所の精査
            original_storage_location = None
            if line[IDX_ORIGINAL_STORAGE_LOCATION]:
                for k, v in original_storage_location_dict().items():
                    if v == line[IDX_ORIGINAL_STORAGE_LOCATION]:
                        original_storage_location = str(k)

            # 相手方法人番号
            partner_corporate_number = line[IDX_PARTNER_CORPORATE_NUMBER].strip() if line[IDX_PARTNER_CORPORATE_NUMBER].strip() else None

            for r in rec:
                info('debug import 4')
                r.pdf_path = line[IDX_PDF_PATH]
                r.contract_title = zenhan(line[IDX_CONTRACT_TITLE])
                r.signing_target_kou = ''
                r.signing_target_otsu = ''
                r.contract_companies = zenhan(line[IDX_CONTRACT_COMPANIES])
                r.signing_date = signing_date
                r.signing_date_disp = signing_date_disp
                r.expiration_date = expiration_date
                r.expiration_date_disp = expiration_date_disp
                r.auto_update = auto_update
                r.file_name = zenhan(file_name)
                r.remarks = remarks
                r.hidden_flag = hidden_flag
                r.contract_termination_flag = contract_termination_flag
                r.original_classification = original_classification
                r.loan_guarantee_availability = line[IDX_LOAN_GUARANTEE_AVAILABILITY]
                r.ringi_no = line[IDX_RINGI_NO]
                r.ringi_url = ''
                r.document_number = line[IDX_DOCUMENT_NUMBER]
                r.original_storage_location = original_storage_location
                r.deleted_flag = False
                r.create_user = request.user.username
                r.modify_user = request.user.username
                r.partner_corporate_number = partner_corporate_number
                info("doc_number:" + line[IDX_DOCUMENT_NUMBER])
                r.save()
                # 実行対象を保持
                view_id_list.append(r.id)

            # 管轄社名の処理
            # 中間テーブルの削除
            IndexLocalCompany.objects.filter(index_id=line[IDX_NO]).delete()
            #  []管轄社名,
            tmp = []

            # 管轄社法人番号（元）
            if line[IDX_BASE_LOCALCOMPANIES_NUMBER].replace("'", ''):
                for lc in line[IDX_BASE_LOCALCOMPANIES_NUMBER].replace("'", '').split(','):
                    lc2 = LocalCompany.objects.filter(id=lc)
                    for l in lc2:
                        IndexLocalCompany.objects.create(
                            index_id=line[IDX_NO],
                            local_company_id=l.id,
                            add_flg=0,
                        )
                        tmp.append(l.id)

            # 追加管轄社法人番号
            additional_numbers = []
            if line[IDX_ADDITIONAL_LOCALCOMPANIES_NUMBER].replace("'", ''):
                for lc in line[IDX_ADDITIONAL_LOCALCOMPANIES_NUMBER].replace("'", '').split(','):
                    lc2 = LocalCompany.objects.filter(id=lc)
                    for l in lc2:
                        IndexLocalCompany.objects.create(
                            index_id=line[IDX_NO],
                            local_company_id=l.id,
                            add_flg=1,
                        ).save()
                        tmp.append(l.id)
                        additional_numbers.append(lc)

            # 除外管轄社法人番号
            if line[IDX_EXCLUSION_LOCALCOMPANIES_NUMBER].replace("'", ''):
                for lc in line[IDX_EXCLUSION_LOCALCOMPANIES_NUMBER].replace("'", '').split(','):
                    lc2 = LocalCompany.objects.filter(id=lc)
                    
                    if lc in additional_numbers:
                        for al in IndexLocalCompany.objects.filter(
                            index_id=line[IDX_NO],
                            local_company_id=lc
                        ):
                            al.add_flg=3
                            al.save()                        
                    else:
                        for l in lc2:
                            IndexLocalCompany.objects.create(
                                index_id=line[IDX_NO],
                                local_company_id=l.id,
                                add_flg=2
                            )
            line_num += 1

        # ログ:CSVインポート
        info(str(inserted_records) + ' record(s) is(are) inserted with csv by user id[' + request.session[
            '_auth_user_id'] + '].(' + json.dumps(request.POST, ensure_ascii=False) + ')')
        result += str(inserted_records) + '件のインポートを実行しました。'
    else:
        result += 'インポートをキャンセルしました。'
    # 今回挿入分のみにする
    indexes = Index.objects.filter(id__in=uploaded_rec_list)
    indexes = indexes.filter(deleted_flag=False)
    # スーパーユーザでなければ管轄社で表示を絞る
    if not request.user.is_superuser:
        info('デバッグ用:csv更新インポート6')
        # 管轄社の処理
        lc_list = list()
        src_list = list()
        # 新形式 2019/05/21
        rlc = RestrictLocalCompany.objects.filter(user_id=request.user.id)
        if rlc:
            for r in rlc:
                src_list.append(r.local_company_id)
            # # LC1
            # if request.user.has_perm('contract_index.access_lc1'):
            #     src_list.append(1)
            # # LC2
            # if request.user.has_perm('contract_index.access_lc2'):
            #     src_list.append(2)
            # # LC3
            # if request.user.has_perm('contract_index.access_lc3'):
            #     src_list.append(3)
            # # LC4
            # if request.user.has_perm('contract_index.access_lc4'):
            #     src_list.append(4)
            # # LC5
            # if request.user.has_perm('contract_index.access_lc5'):
            #     src_list.append(5)
            # # LC6
            # if request.user.has_perm('contract_index.access_lc6'):
            #     src_list.append(6)
            for i in IndexLocalCompany.objects.filter(local_company_id__in=src_list):
                lc_list.append(i.index_id)
            indexes = indexes.filter(id__in=lc_list)
    # hidden_flagの処理
    if not request.user.has_perm('contract_index.view_hidden'):
        indexes = indexes.filter(hidden_flag=False)
    # 管轄社カラム用
    if request.user.has_perm('contract_index.read_localcompany'):
        indexes = indexes.prefetch_related('localcompanies')
    info('デバッグ用:csv更新インポート7')
    content = {
        'name': request.user,
        # 削除フラグは取得しない
        # 'indexes': Index.objects.all(),
        'indexes': indexes.order_by('-id'),
        'indexes_localCompanies': IndexLocalCompany.objects.all(),
        'result': result,
        'original_classification_dict': original_classification_dict().items(),
        'original_storage_location_dict': original_storage_location_dict().items(),
    }
    return render(request, 'contract_index/index.html', content)


@login_required
def manage_ll(request):
    '''
    管轄社管理機能
    '''
    if 'method' not in request.POST:
        content = {
            'name': request.user,
            'localcompanies': LocalCompany.objects.all()
        }
        return render(request, 'contract_index/localcompany.html', content)
    # 統合する
    if request.POST['method'] == 'combine':
        # 統合先のIDをnameから調べる
        merger_id = ''
        rec = LocalCompany.objects.filter(
            local_company_name=request.POST['new_name'])
        for r in rec:
            merger_id = r.id #法人番号
        # 統合前のIDを統合先に変更
        rec = IndexLocalCompany.objects.filter(
            local_company_id=request.POST['id'])
        for r in rec:
            IndexLocalCompany(
                index_id=r.index_id,
                local_company_id=merger_id,
            ).save()
        # 統合前の管轄社を削除
        LocalCompany.objects.filter(id=request.POST['id']).delete()
        result = 'No.' + request.POST['id'] + 'を「' + \
            request.POST['new_name'] + '」に統合しました。'
    # 変更する
    elif request.POST['method'] == 'change':
        rec = LocalCompany.objects.filter(id=request.POST['id'])
        for r in rec:
            r.local_company_name = request.POST['new_name']
            r.save()
        result = 'No.' + request.POST['id'] + 'を「' + \
            request.POST['new_name'] + '」に変更しました。'
    # ID変更する
    elif request.POST['method'] == 'change_id':
        rec = LocalCompany.objects.filter(id=request.POST['old_id'])
        for r in rec:
            r.id = request.POST['id']
            r.save()

        rec = IndexLocalCompany.objects.filter(local_company_id=request.POST['old_id'])
        for r in rec:
            r.local_company_id = request.POST['id']
            r.save()

        rec = RestrictLocalCompany.objects.filter(local_company_id=request.POST['old_id'])
        for r in rec:
            r.local_company_id = request.POST['id']
            r.save()

        LocalCompany.objects.filter(id=request.POST['old_id']).delete()
        result = 'No.' + request.POST['old_id'] + 'を「' + \
                 request.POST['id'] + '」に変更しました。'
    # ID, 社名変更
    elif request.POST['method'] == 'change_with_id':
        rec = LocalCompany.objects.filter(id=request.POST['old_id'])
        for r in rec:
            r.local_company_name = request.POST['new_name']
            r.id = request.POST['id']
            r.save()

        rec = IndexLocalCompany.objects.filter(local_company_id=request.POST['old_id'])
        for r in rec:
            r.local_company_id = request.POST['id']
            r.save()

        rec = RestrictLocalCompany.objects.filter(local_company_id=request.POST['old_id'])
        for r in rec:
            r.local_company_id = request.POST['id']
            r.save()

        LocalCompany.objects.filter(id=request.POST['old_id']).delete()
        result = 'No.' + request.POST['old_id'] + 'を「' + \
                 request.POST['id'] + '」に変更しました。'

    # ID変更, 社名統合する
    elif request.POST['method'] == 'combine_with_id':
        # 統合先のIDをnameから調べる
        merger_id = ''
        rec = LocalCompany.objects.filter(
            local_company_name=request.POST['new_name'])
        for r in rec:
            merger_id = r.id  # 法人番号
        # 統合前のIDを統合先に変更
        rec = IndexLocalCompany.objects.filter(
            local_company_id=request.POST['old_id'])
        for r in rec:
            IndexLocalCompany(
                index_id=r.index_id,
                local_company_id=merger_id,
            ).save()
        # 統合前の管轄社を削除
        LocalCompany.objects.filter(id=request.POST['old_id']).delete()
        result = 'No.' + request.POST['old_id'] + 'を「' + \
                 request.POST['new_name'] + '」に統合しました。'

    # 削除する
    elif request.POST['method'] == 'remove':
        rec = IndexLocalCompany.objects.filter(
            local_company_id=request.POST['id'])

        if len(rec) == 0:
            LocalCompany.objects.filter(id=request.POST['id']).delete()
            result = 'No.' + request.POST['id'] + 'を削除しました。'
        else:
            result = request.POST['id'] + 'は会社情報に設定されているので削除できません。'
    # 追加する
    elif request.POST['method'] == 'add':
        LocalCompany(
            local_company_name=request.POST['new_name'],
            id=request.POST['id']
        ).save()
        result = '「' + request.POST['new_name'] + '」' + 'を追加しました。'
    else:
        return HttpResponse('想定外のエラー')
    content = {
        'name': request.user,
        'result': result,
        'localcompanies': LocalCompany.objects.all()
    }
    return render(request, 'contract_index/localcompany.html', content)


@login_required
def restrictlocalcompany(request):
    '''
    管轄社制限管理機能への繊維
    '''
    content = {
        'name': request.user,
        'localcompanies': LocalCompany.objects.all().order_by('local_company_name'),
        'restrictlocalcompany': RestrictLocalCompany.objects.all(),
        'users': User.objects.all()
    }
    return render(request, 'contract_index/restrictlocalcompany.html', content)


@login_required
def restrictlocalcompanydetails(request):
    '''
    管轄社制限処理
    '''
    if 'id' in request.POST:
        user_id = request.POST['id']
        user_a = User.objects.filter(id=user_id)
        for u in user_a:
            user = u
        # 変更処理
        if 'submit' in request.POST:
            RestrictLocalCompany.objects.filter(user_id=user_id).delete()
            for lc_id in request.POST.getlist('restrictlocalcompany'):
                RestrictLocalCompany(
                    user_id=user_id,
                    local_company_id=lc_id
                ).save()
            # ログ:レコード 変更
            info('user id[' + user_id + "]'s localcompany permissions are updated by user id[" + request.session[
                '_auth_user_id'] + '].(' + json.dumps(request.POST, ensure_ascii=False) + ')(対象会社:' + ','.join(
                request.POST.getlist('restrictlocalcompany')) + ')')
            result = 'ユーザー名"' + user.username + '"の管轄社制限を変更しました。'
            content = {
                'result': result,
                'name': request.user,
                'localcompanies': LocalCompany.objects.all().order_by('local_company_name'),
                'restrictlocalcompany': RestrictLocalCompany.objects.all(),
                'users': user_a
            }
            return render(request, 'contract_index/restrictlocalcompany.html', content)
        # 変更前 詳細表示
        result = 'ユーザー名"' + user.username + '"の管轄社制限を変更します。'
        content = {
            'result': result,
            'name': request.user,
            'localcompanies': LocalCompany.objects.all().order_by('local_company_name'),
            'restrictlocalcompany': RestrictLocalCompany.objects.all(),
            'user': user
        }
        return render(request, 'contract_index/restrictlocalcompanydetails.html', content)
    else:
        restrictlocalcompany(request)


@login_required
def restrictlocalcompanycopy(request):
    '''
    管轄社制限のコピー
    '''
    if 'id' in request.POST and 'targets' in request.POST:
        for target_user in request.POST['targets'].split(','):
            RestrictLocalCompany.objects.filter(user_id=target_user).delete()
        rlcs = RestrictLocalCompany.objects.filter(user_id=request.POST['id'])
        for target_user in request.POST['targets'].split(','):
            for rlc in rlcs:
                RestrictLocalCompany(
                    user_id=target_user,
                    local_company_id=rlc.local_company_id
                ).save()
        # user_id = request.POST['id']
        # user_a = User.objects.filter(id=user_id)
        # for u in user_a:
        #     user = u
        # # 変更処理
        # if 'submit' in request.POST:
        #     RestrictLocalCompany.objects.filter(user_id=user_id).delete()
        #     for lc_id in request.POST.getlist('restrictlocalcompany'):
        #         RestrictLocalCompany(
        #             user_id=user_id,
        #             local_company_id=lc_id
        #         ).save()
        #     # ログ:レコード 変更
        #     info('user id[' + user_id + "]'s localcompany permissions are updated by user id[" + request.session['_auth_user_id'] + '].')
        #     result = 'ユーザー名"' + user.username + '"の管轄社制限を変更しました。'
        #     content = {
        #         'result': result,
        #         'name': request.user,
        #         'localcompanies': LocalCompany.objects.all(),
        #         'restrictlocalcompany': RestrictLocalCompany.objects.all(),
        #         'users': user_a
        #     }
        #     return render(request, 'contract_index/restrictlocalcompany.html', content)
        # 変更前 詳細表示
        info('user id[' + request.POST['id'] + "]'s localcompany permissions copy to " + request.POST[
            'targets'] + " by user id[" + request.session['_auth_user_id'] + '].(' + json.dumps(request.POST,
                                                                                                ensure_ascii=False) + ')')
        result = 'No."' + request.POST['id'] + \
            '"の管轄社制限を' + request.POST['targets'] + 'にコピーしました。'
        content = {
            'result': result,
            'name': request.user,
            'localcompanies': LocalCompany.objects.all(),
            'restrictlocalcompany': RestrictLocalCompany.objects.all(),
            'users': User.objects.all()
        }
        return render(request, 'contract_index/restrictlocalcompany.html', content)
    else:
        restrictlocalcompany(request)


@login_required
def confirmation(request):
    """
    一括反映確認画面への遷移です。
    """
    # 直接アクセス不可
    if not request.POST:
        return redirect('contract_index:search')

    # 対象のidリスト
    target_id_list = request.POST.getlist('target_id_list')

    indexes = Index.objects.all()

    view_indexs = list()
    for i_id in target_id_list:
        index = indexes.filter(id=i_id)
        if not index[0]:
            continue
        i = index[0]
        view_indexs.append({
            'id': i_id,
            'contract_title': i.contract_title,
            'contract_companies': request.POST.get('update[' + str(i_id) + '][contract_companies]'),
            'base': request.POST.get('update[' + i_id + '][base_localcompany_number]'),
            'add': request.POST.get('update[' + i_id + '][add_localcompany_number]'),
            'delete': request.POST.get('update[' + i_id + '][delete_localcompany_number]'),
            'after': request.POST.get('update[' + i_id + '][after_localcompany_number]')
        })

    # POSTの再送信
    post_dict = dict(six.iterlists(request.POST))

    content = {
        'post_dict': post_dict,
        'view_indexs': view_indexs,
        'target_id_list': target_id_list,
    }
    return render(request, 'contract_index/confirmation.html', content)


def csrf_failure(request, reason=''):
    return render(request, '403.html')


def date_check(str):
    '''
    日付のチェック用

    Parameters
    ----------
    str : string
        日付形式化を判定する文字列

    Returns
    -------
    result : bool
        正しい日付形式ならTrue(yyyy/mm/dd)
    '''
    try:
        datelist = str.split('/')
        if (1900 <= int(datelist[0]) <= 3000) and \
                (1 <= int(datelist[1]) <= 12) and \
                (1 <= int(datelist[2]) <= 31):
            return True
        return False
    except:
        return False


def date_scrutinizer(date_str):
    '''
    想定される日付形式をSQLDB用に精査調整します。

    Parameters
    ----------
    date_str: string
        不適な日付形式を含む日付

    Returns
    -------
    date_date: string
        (yyyy-mm-dd)に精査された日付形式
    '''
    if date_str:
        try:
            date_date = date_str.replace('/', '-') \
                .replace('.', '-') \
                .replace('(', '') \
                .replace(')', '') \
                .replace('吉日', '') \
                .replace('末日', '31日') \
                .replace('●', '') \
                .replace('問題', '') \
                .strip('/') \
                .strip('-') \
                .strip('.')
            # 和暦変換
            if '昭和元年' in date_date:
                date_date = date_date.replace('昭和元年', '1926年')
            elif '昭和' in date_date:
                ad = int(date_date[:date_date.find('年')].replace('昭和', ''))
                date_date = re.sub('昭和\d*年', str(ad + 1925) + '年', date_date)
            if '平成元年' in date_date:
                date_date = date_date.replace('平成元年', '1989年')
            elif '平成' in date_date:
                ad = int(date_date[:date_date.find('年')].replace('平成', ''))
                date_date = re.sub('平成\d*年', str(ad + 1989) + '年', date_date)
            # 年月日の処理
            if '年' in date_date:
                if '月' in date_date:
                    date_date = date_date.replace('年', '-')
                    if '日' in date_date:
                        date_date = date_date.replace('月', '-')
                        date_date = date_date.replace('日', '')
                    else:
                        date_date = date_date.replace('月', '')
                else:
                    date_date = date_date.replace('年', '')
            # 年月日がある場合
            if len(date_date) >= 8 and '-' in date_date:
                pass
            # 年月の場合
            elif len(date_date) >= 6 and '-' in date_date:
                date_date += '-1'
            # 年の場合
            elif len(date_date) == 4 and date_date.isdecimal():
                date_date += '-1-1'
            # その他
            else:
                date_date = None
            # 全角半角変換
            date_date = date_date.replace('０', '0') \
                .replace('１', '1') \
                .replace('２', '2') \
                .replace('３', '3') \
                .replace('４', '4') \
                .replace('５', '5') \
                .replace('６', '6') \
                .replace('７', '7') \
                .replace('８', '8') \
                .replace('９', '9')
            # 日付として正しいかチェック
            if not (1000 <= int(date_date.split('-')[0]) <= 3000 and
                    1 <= int(date_date.split('-')[1]) <= 12 and
                    1 <= int(date_date.split('-')[2]) <= 31):
                date_date = None
            if date_date.count('-') >= 3:
                date_date = None
            date_date = date_date.replace('2-30', '2-29') \
                .replace('2-31', '2-29') \
                .replace('4-31', '4-30') \
                .replace('6-31', '6-30') \
                .replace('9-31', '9-30') \
                .replace('11-31', '11-30') \
                .strip()
            # うるう年対応
            if ('-2-29' in date_date) or ('-02-29' in date_date):
                y = int(date_date[0:4])
                if y % 4 == 0:
                    if y % 100 == 0:
                        if y % 400 == 0:
                            pass
                        else:
                            date_date = date_date.replace('2-29', '2-28')
                    else:
                        pass
                else:
                    date_date = date_date.replace('2-29', '2-28')
        except:
            date_date = None
    else:
        date_date = None
    return date_date


def remote_addr_check(request):
    ip_addr = request.META['REMOTE_ADDR']
    return render(request,
                  'remote_addr.html',
                  {'ip_addr': ip_addr}
                  )


# 廃止
# def csv_exported(request):
#     # ログ：CSV出力
#     info('csv is exported by user id[' + request.session['_auth_user_id'] + '].')
#     content = {
#         'name': request.user,
#         'result': 'CSVをエクスポートしました。',
#     }
#     return render(request, 'contract_index/searchresult.html', content)

def kouotsu_changer(dic):
    '''
    辞書形式の甲乙入替え
    '''
    if 'signing_target_kou__iexact' in dic and 'signing_target_otsu__iexact' in dic:
        temp = dic['signing_target_kou__iexact']
        dic['signing_target_kou__iexact'] = dic['signing_target_otsu__iexact']
        dic['signing_target_otsu__iexact'] = temp
    elif 'signing_target_kou__iexact' in dic:
        dic['signing_target_otsu__iexact'] = dic['signing_target_kou__iexact']
        del dic['signing_target_kou__iexact']
    elif 'signing_target_otsu__iexact' in dic:
        dic['signing_target_kou__iexact'] = dic['signing_target_otsu__iexact']
        del dic['signing_target_otsu__iexact']
    else:
        pass

    if 'signing_target_kou__icontains' in dic and 'signing_target_otsu__icontains' in dic:
        temp = dic['signing_target_kou__icontains']
        dic['signing_target_kou__icontains'] = dic['signing_target_otsu__icontains']
        dic['signing_target_otsu__icontains'] = temp
    elif 'signing_target_kou__icontains' in dic:
        dic['signing_target_otsu__icontains'] = dic['signing_target_kou__icontains']
        del dic['signing_target_kou__icontains']
    elif 'signing_target_otsu__icontains' in dic:
        dic['signing_target_kou__icontains'] = dic['signing_target_otsu__icontains']
        del dic['signing_target_otsu__icontains']
    else:
        pass
    return dic


# ログ用関数
def info(msg):
    logger = logging.getLogger('command')
    logger.info(msg)


# 全角半角精査
def zenhan(txt):
    # windowsではmojimojiがインストールできなかったための処理
    if txt == '' or txt is None:
        return ''
    if os.name == 'nt':
        return txt
    else:
        import mojimoji
        return mojimoji.zen_to_han(mojimoji.han_to_zen(txt), kana=False)


def redirectRingiNum(request, ringi_num):
    url = returnURL(str(ringi_num))
    return JsonResponse({'url': url}, status=200, content_type="application/json")

# 稟議URL取得
def getRingiURL(code):
    code_list = code.split(',')
    value = ''
    for each_code in code_list:
        value += returnURL(each_code)
        value += ','
    return value


def returnURL(code):
    # ringi_path = os.path.join('ringi.json')
    ringi_path = os.path.join('/var/www/upload/ringi.json')
    ringi_json = open(ringi_path,'r',encoding='utf-8')
    ringi_data = json.load(ringi_json)
    ringi_url = ''
    ringi_check = 0
    for ele in ringi_data['ringi_approval']:
        if str(ele['ringi']) == code:
            ringi_check = 1
            ringi_url += 'https://ringi.hikari.co.jp/ringi/show/id/' + str(ele['id'])
            break
    if ringi_check == 0:
        ringi_url += 'https://ringi.hikari.co.jp/search/list?filter%5Bnumber%5D=' + str(code)
    return ringi_url
