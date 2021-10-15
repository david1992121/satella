// jQueryプラグインのtable2csvでは文字コードが変更できないので
// 新たに作っています。参考 : http://blog.adjust-work.com/1019/
var tableToCSV2 = {
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
            // 最終行は読み込まない
            if(cols[0]['textContent'] === '-'){
                break;
            }
            for (var j = 0, numOfCols = cols.length; j < numOfCols; j++) {
                var text = cols[j].textContent || cols[j].innerText;
                text = '"' + text.replace(/"/g, '""') + '"';
                // 不要部の除去
                // 変更ボタン、削除ボタン、新規追加ボタンの除去
                if (isHeadingScrutinyCount < 2 && text == '""'){
                    isHeadingScrutinyCount++;
                    continue;
                }
                if(text.indexOf('変更')!= -1 || text.indexOf('削除')!= -1 || text.indexOf('新規追加')!= -1) {
                    // console.log(text);
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
        return Util2.getNodesByName(elm, 'tr');
    },

    getCols: function (elm) {
        return Util2.getNodesByName(elm, ['td', 'th']);
    }
}

var Util2 = {
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

function download2(uri, filename) {
    filename = filename || 'file';
  
    var link = document.createElement('a');
    link.download = filename;
    link.href = uri;
    link.click();
}

window.onload = function () {
    document.getElementById('downloadCsvBtn4ll').addEventListener('click', function (e) {
        // 文字コードの変換 Encoding.jsを利用する
        var csv = tableToCSV2.export(document.getElementById('table4ll'));

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
    });
}