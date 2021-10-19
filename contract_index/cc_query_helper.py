from django.db.models import Q
from .models import Index
from django.db.models.expressions import RawSQL

def add_extra_query(pack_item):
    return_query = Q()
    extra_query = []
    exact_num = 0
    contain_num = 0
    skip_index = []
    for index, key_item in enumerate(pack_item):
        if index in skip_index:
            continue
        exact_num = 1 if key_item["is_exact"] else 0
        contain_num = 1
        for other_index, other_key_item in enumerate(pack_item):
            if other_index == index:
                continue
            if key_item["keyword"] == other_key_item["keyword"]:
                skip_index.append(other_index)
                if other_key_item["is_exact"]:
                    exact_num += 1
            if key_item["keyword"] in other_key_item["keyword"]:
                contain_num += 1
        # print(index, exact_num, contain_num)
        if exact_num > 1:
            temp_key_array = []
            for _ in range(exact_num):
                temp_key_array.append("/{}/".format(key_item["keyword"]))

            extra_query.append("%{}%".format("%".join(temp_key_array)))
            # extra_query &= Q(contract_companies__icontains = "%%".join(temp_key_array))
        if contain_num > 1:
            temp_key_array = []
            for _ in range(contain_num):
                temp_key_array.append(key_item["keyword"])
            extra_query.append("%{}%".format("%".join(temp_key_array)))
            # extra_query &= Q(contract_companies__icontains = "%%".join(temp_key_array))
    

    if len(extra_query) > 0:
        try:
            extra_array = ["contract_companies like %s" for _ in extra_query]
            # print(extra_array)
            query = "SELECT id FROM contract_index_index where {}".format(" AND ".join(extra_array))
            # print(query)
            return_query &= Q(id__in = RawSQL(query, extra_query))

            # print(Index.objects.filter(id__in = RawSQL(query, extra_query)).count())
        except Exception as e:
            print("ERROR OCCURED")
            print(e)

    # print(return_query)
    return return_query

# 契約当事者のクエリ作成
def make_cc_query(keyword_pack):
    
    if len(keyword_pack) > 0:
        return add_extra_query(keyword_pack)
    else:
        return Q()
        

# 管轄社法人番号のクエリ作成
def make_cn_query(keyword_pack):

    if len(keyword_pack) > 0:
        query_set = Index.objects.all()
        for pack_item in keyword_pack:
            query = Q(index__local_company_id = pack_item["keyword"])
            sub_query = None
            for flag_item in pack_item["add_flg"]:
                if sub_query == None:
                    sub_query = Q(index__add_flg = flag_item)
                else:
                    sub_query |= Q(index__add_flg = flag_item)
            query &= sub_query
            query_set = query_set.filter(query)
        return Q(id__in = query_set.values_list("id", flat=True))
    else:
        return Q()