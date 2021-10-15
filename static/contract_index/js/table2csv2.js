// jQueryプラグインのtable2csvでは文字コードが変更できないので
// 新たに作っています。参考 : http://blog.adjust-work.com/1019/
var tableToCSV = {
    export: function (elm /*, delimiter */) {
        var table = elm;
        var rows = this.getRows(table);
        var lines = [];
        var delimiter = delimiter || ',';
        var isHeadingScrutinyCount = 0;
        var is1stcell = true;

        for (var i = 0, numOfRows = rows.length; i < numOfRows; i++) {
            var cols = this.getCols(rows[i]);
            var line = [];

            for (var j = 0, numOfCols = cols.length; j < numOfCols; j++) {
                var text = cols[j].textContent || cols[j].innerText;
                text = '"' + text.replace(/"/g, '""') + '"';
                // 不要部の除去
                // PDF列の除去
                if (is1stcell){
                    is1stcell = false;
                    continue;
                }
                // 編集ボタン、結果から除外ボタンの除去
                if (isHeadingScrutinyCount < 2 && text == '""'){
                    isHeadingScrutinyCount++;
                    continue;
                }
                if(text.indexOf('結果から除外')!= -1 || text.indexOf('編集')!= -1) {
                    console.log(text);
                    continue;
                }
                
                line.push(text);
                // console.log(line);
            }
            is1stcell = true;

            lines.push(line.join(delimiter));
        }

        return lines.join("\r\n");
    },

    getRows: function (elm) {
        return Util.getNodesByName(elm, 'tr');
    },

    getCols: function (elm) {
        return Util.getNodesByName(elm, ['td', 'th']);
    }
}

var Util = {
    getNodesByName: function (elm /*, string or array*/) {
        var children = elm.childNodes;
        var nodeNames = ('string' === typeof arguments[1]) ? [arguments[1]] : arguments[1];
        nodeNames = nodeNames.map(function (str) { return str.toLowerCase() });

        var results = [];

        for (var i = 0, max = children.length; i < max; i++) {
            if (nodeNames.indexOf(children[i].nodeName.toLowerCase()) !== -1) {
                results.push(children[i]);
            }
            else {
                results = results.concat(this.getNodesByName(children[i], nodeNames));
            }
        }

        return results;
    }
}

function download(uri, filename) {
    filename = filename || 'file';
  
    var link = document.createElement('a');
    link.download = filename;
    link.href = uri;
    link.click();
}

window.onload = function () {
    document.getElementById('downloadCsvBtn').addEventListener('click', function (e) {
        // 文字コードの変換 Encoding.jsを利用する
        var csv = tableToCSV.export(document.getElementById('sorter'));

        var sjisArray = Encoding.convert(Encoding.stringToCode(csv), { to: 'SJIS' });

        var blob = new Blob([new Uint8Array(sjisArray)], { type: 'text/csv' });
        // $("#csv_exported")[0].click(); ページ遷移廃止
        // クロスブラウザ対応
        if (window.navigator.msSaveBlob) {
            e.preventDefault();
            window.navigator.msSaveBlob(blob, this.getAttribute('download'));
        }
        else {
            this.href = URL.createObjectURL(blob);
        }
        // PDFダウンロード機能ここから
        // if(window.confirm("PDFもダウンロードをしますか？\n(ネットワークドライブ内のファイルは現時点では対応していません。)")) {
        //     // ダウンロードの処理を記述
        //     var csvlist = csv.replace(/\"/g,'').split(',');
        //     for (var i = 0; i < csvlist.length; i++) {
        //         if (csvlist[i].match(/.pdf/)){
        //             console.log(csvlist[i]);


        //             // $("#pdf_link")[0].click();
                    
        //             // API利用
        //             // var reader = new FileReader();
        //             // ファイルの読み込みに成功したら、その内容を<img id="result">に反映
        //             // reader.addEventListener('load', function(e) {
        //             //     document.querySelector("#result").src = reader.result;
        //             // }, true);
        //             // ファイルの内容をData URL形式で取得（1）
        //             // var pdfBlob = new Blob(csvlist[i], {type: "pdf"});
        //             // var pdfBlob2 = reader.readAsDataURL(pdfBlob);
        //             // download(pdfBlob2, csvlist[i].split('\\')['length']);
                    

        //             // download(csvlist[i], csvlist[i].split('\\')['length']);
        //         }
        //     }
        // }
        // else {
        //     // 何もしない
        // }
    });
}