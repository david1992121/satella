from django.db import models
from django.contrib.auth import get_user_model

# テーブルの定義
class Index(models.Model):
    """
    メインとなる契約書テーブルです。
    """
    # IDは自動生成
    # 契約書名
    contract_title = models.CharField(max_length=500, db_index=True)
    # 締結先_甲 FK
    # signing_target_kou = models.ForeignKey('Company', related_name='signing_target_kou', default=0, on_delete=models.SET_DEFAULT)
    signing_target_kou = models.CharField(max_length=2000)
    # 締結先_乙 FK
    # signing_target_otsu = models.ForeignKey('Company', related_name='signing_target_otsu', default=0, on_delete=models.SET_DEFAULT)
    signing_target_otsu = models.CharField(max_length=2000)
    # 締結日表示用
    signing_date_disp = models.CharField(null=True, blank=True, max_length=200)
    # 締結日
    signing_date = models.DateField(null=True, blank=True, db_index=True)
    # 有効期限表示用
    expiration_date_disp = models.CharField(null=True, blank=True, max_length=200)
    # 有効期限
    expiration_date = models.DateField(null=True, blank=True, db_index=True)
    # 自動更新
    auto_update = models.NullBooleanField(null=True, blank=True)
    # ファイル名
    file_name = models.CharField(null=True, blank=True, max_length=200, db_index=True)
    # PDF
    pdf_path = models.CharField(null=True, blank=True, max_length=2000)
    # 備考
    remarks = models.CharField(null=True, blank=True, max_length=2000)
    # 非表示フラグ
    hidden_flag = models.BooleanField(default=False)
    # 管轄社ID FK
    # local_company_id = models.ForeignKey('LocalCompany', default=0, on_delete=models.SET_DEFAULT)
    # 作成日
    create_date = models.DateTimeField(auto_now_add=True)
    # 最終更新日
    modify_date = models.DateTimeField(auto_now=True)
    # 削除フラグ
    deleted_flag = models.BooleanField(default=False)
    # 作成ユーザー
    create_user = models.CharField(null=True, blank=True, max_length=200)
    # 最終更新ユーザー
    modify_user = models.CharField(null=True, blank=True, max_length=200)
    # 多対多フィールド
    localcompanies = models.ManyToManyField('LocalCompany', through='IndexLocalCompany')
    # 契約終了フラグ
    contract_termination_flag = models.BooleanField(default=False)
    # 契約当事者（締結先甲乙がまとめて入るようになる）
    contract_companies = models.CharField(max_length=2000, default='')
    # 原本区分
    original_classification = models.CharField(null=True, max_length=200)
    # 原本保管場所
    original_storage_location = models.CharField(null=True, max_length=200)
    # 光通信Grpの債務保証有無
    loan_guarantee_availability = models.CharField(null=True, max_length=200)
    # 書面番号
    document_number = models.CharField(null=True, max_length=200)
    # 保管場所URL
    storage_location_url = models.CharField(null=True, max_length=1000)
    # 稟議URL
    ringi_url = models.CharField(null=True, max_length=1000)
    # 稟議番号
    ringi_no = models.CharField(null=True, max_length=100)
    # 相手先法人番号
    partner_corporate_number = models.CharField(null=True, max_length=300)

    def __str__(self):
        # return u"{0}:{1}... ".format(self.id, self.contract_title)
        return self.contract_title

    def get_localcompanies(self):
        '''
        管轄社をリストで返します
        '''
        companies = IndexLocalCompany.objects.filter(index=self)
        return [IndexLocalCompany.local_company for company in companies]

    def ringinolist(self):
        if self.ringi_no:
            return self.ringi_no.split(",")

    def ringiurllist(self):
        if self.ringi_url:
            return self.ringi_url.split(",")

class LocalCompany(models.Model):
    """
    管轄社テーブルです。
    """
    id = models.CharField(max_length=13, primary_key=True)
    # 管轄社名
    local_company_name = models.CharField(max_length=200)
    # 作成日
    create_date = models.DateTimeField(auto_now_add=True)
    # 最終更新日
    modify_date = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.local_company_name

# 中間テーブル
class IndexLocalCompany(models.Model):
    """
    契約書・管轄社を多対多で処理する中間テーブルです。
    """
    index = models.ForeignKey('Index', related_name='index', on_delete=models.CASCADE)
    local_company = models.ForeignKey('LocalCompany', related_name='local_company', on_delete=models.CASCADE)
    add_flg = models.IntegerField(default=0)
    # def __str__(self):
    #     return self.local_company_name

class RestrictLocalCompany(models.Model):
    """
    ユーザー・管轄社を多対多で処理する中間テーブル。
    """
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)
    # user_id = models.IntegerField()
    local_company = models.ForeignKey('LocalCompany', related_name='restrict_local_company', on_delete=models.CASCADE)
    # local_company_id = models.IntegerField()


# class Company(models.Model):
#     """
#     会社テーブルです。
#     """
#     # 会社名
#     company_name = models.CharField(max_length=200)
#     # カナ
#     company_kana = models.CharField(max_length=200)
#     # 別名ID(可変長)
#     synonym_id = models.CharField(max_length=200)
#     # # 法人番号
#     # corporation_number = models.BigIntegerField()
#     # 作成日
#     create_date = models.DateTimeField(auto_now_add=True)
#     # 最終更新日
#     modify_date = models.DateTimeField(auto_now=True)

#     def __str__(self):
#         return self.company_name