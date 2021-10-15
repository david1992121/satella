// 長いテキストの折返しの挙動用のJSです。
// CSSでデフォルト状態は折りたたみしています。
$(function(){
    // クリック時に展開します。
    $(".textwrap").click(
        function() {
            $(this).css({
                'text-overflow':'clip',
                'overflow': 'visible',
                'white-space': 'normal',
                'word-wrap': 'break-word',
            });
        }
    );
    // 要素からマウスが離れた時(hover-out)に折りたたみます。
    $(".textwrap").hover(
        function() {
        },
        function() {
            $(this).css({
                'text-overflow': 'ellipsis',
                'overflow': 'hidden',
                'white-space': 'nowrap',
            });
        }
    );
    // // 管轄社ID列用
    // // クリック時に展開します。
    // $(".textwrap2").click(
    //     function() {
    //         $(this).css({
    //             'max-height': 'none'
    //             // 'text-overflow':'clip',
    //             // 'overflow': 'visible',
    //             // 'white-space': 'normal',
    //             // 'word-wrap': 'break-word',
    //         });
    //     }
    // );
    // // 要素からマウスが離れた時(hover-out)に折りたたみます。
    // $(".textwrap2").hover(
    //     function() {
    //     },
    //     function() {
    //         $(this).css({
    //             'max-height': '65px'
    //             // 'display': '-webkit-box',
    //             // '-webkit-box-orient': 'vertical',
    //             // '-webkit-line-clamp': 3,
    //             // 'overflow': 'hidden',
    //             // 'text-overflow': 'ellipsis',
    //             // 'overflow': 'hidden',
    //             // 'white-space': 'nowrap',
    //         });
    //     }
    // );
    // 管轄社制限管理用
    $(".textwrap3").click(
        function() {
            $(this).css({
                'text-overflow':'clip',
                'overflow': 'visible',
                'white-space': 'normal',
                'word-wrap': 'break-word',
            });
        }
    );
    // 要素からマウスが離れた時(hover-out)に折りたたみます。
    $(".textwrap3").hover(
        function() {
        },
        function() {
            $(this).css({
                'text-overflow': 'ellipsis',
                'overflow': 'hidden',
                'white-space': 'nowrap',
            });
        }
    );
});