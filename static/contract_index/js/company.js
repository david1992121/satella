// var companies_name_list = [
// 		{
// 			"id": "1",
// 			"name": "㈱ｱｲﾅｯﾌﾟｽ"
// 		},
// 		{
// 			"id": "4",
// 			"name": "㈱ﾌﾞﾛｰﾄﾞﾋﾟｰｸ"
// 		},
// 		{
// 			"id": "5",
// 			"name": "㈱ｺﾝｽﾃﾚｰｼｮﾝ･ｿﾌﾄｳｪｱ･ｼﾞｬﾊﾟﾝ"
// 		},
// 		{
// 			"id": "7",
// 			"name": "ｱﾙﾃﾞｼｱｲﾝﾍﾞｽﾄﾒﾝﾄ㈱"
// 		}
// 	];


function getCompanyName(company_number){

var list = company_number.split(',');
console.log("list",list);
var result = '';
//var company_list = JSON.parse(companies_name_list);

list.forEach(function (value, index, array) {

	console.log("INDEX",value);
	var filtered = $.grep(companies_name_list,
		function(elem) {
		  return (elem.pk == value);
		}
	);
	console.log("filtered",filtered);
	// if (!Object.keys(filtered).length){
	// 	console.log("filtered",filtered[0].name);
	// }
	if (filtered.length){
		console.log("filtered",filtered[0].name);
		result += filtered[0].fields.local_company_name + "<br />";
	}
});


return result;

}


