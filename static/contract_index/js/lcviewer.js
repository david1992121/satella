function lcviewer(){
    $("#lc_header").hideBalloon();
    var array = [];
    $('[name=local_company] option:selected').each(function() {
        array.push($(this).text());
    });
    $("#lc_header").showBalloon({contents: array.join("<br>"),
                                position: 'right',
                                html: true,
                                css:{
                                    color: "000",
                                    fontSize: '100%',
                                    backgroundColor:"#DFDFDF"}});
    console.log(array);
}

function change_lcviewer(){
    $("#change_lc_header").hideBalloon();
    var array = [];
    $('[name=change_local_company] option:selected').each(function() {
        array.push($(this).text());
    });
    $("#change_lc_header").showBalloon({contents: array.join("<br>"),
                                position: 'right',
                                html: true,
                                css:{
                                    color: "000",
                                    fontSize: '100%',
                                    backgroundColor:"#DFDFDF"}});
    console.log(array);
}

(function () {
    $('#lc_header').append('<button type="button" class="btn-secondary rounded-circle p-0" style="width:2rem;height:2rem;" Onclick=lcviewer();>確認</button>');
    $('#change_lc_header').append('<button type="button" class="btn-secondary rounded-circle p-0" style="width:2rem;height:2rem;" Onclick=change_lcviewer();>確認</button>');
}());