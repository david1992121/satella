from django.urls import path
from . import views

app_name = 'contract_index'

urlpatterns = [
    path('', views.search, name='top'),
    path('index/', views.index, name='index'),
    path('search/', views.search, name='search'),
    path('addrecord/', views.addrecord, name='addrecord'),
    path('import_csv/', views.import_csv, name='import_csv'),
    path('upload/', views.upload, name='upload'),
    path('upload2/', views.upload2, name='upload2'),
    path('changerecord/', views.changerecord, name='changerecord'),
    # path('company/', views.company, name='company'), 廃止
    path('localcompany/', views.local_company, name='localcompany'),
    # path('pdf_download/', views.pdf_download, name='pdf_download'), 廃止
    # path('changerecord/edit/', views.edit, name='edit'), 廃止
    path('addrecord/add_rec/', views.add_rec, name='add_rec'),
    path('search/searchresult/', views.searchresult, name='searchresult'),
    path('searchresult/', views.searchresult, name='searchresult'),
    path('changerecord/searchresult/', views.searchresult, name='searchresult'),
    path('remote_addr/', views.remote_addr_check, name='remote_addr'),
    path('manage_ll/', views.manage_ll, name='manage_ll'),
    path('restrictlocalcompany/', views.restrictlocalcompany, name='restrictlocalcompany'),
    path('restrictlocalcompanydetails/', views.restrictlocalcompanydetails, name='restrictlocalcompanydetails'),
    path('restrictlocalcompanycopy/', views.restrictlocalcompanycopy, name='restrictlocalcompanycopy'),
    # path('csv_exported/', views.csv_exported, name='csv_exported'), 廃止
    path('confirmation/', views.confirmation, name='confirmation'),
    path('api/ringi_redirect/ringi_no/<ringi_num>', views.redirectRingiNum, name="redirect_ringi_num")
]