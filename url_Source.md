########济宁爬虫
##get方法
url_configs = [
            # 济宁市
            {'url_get': 'https://www.jnsggzy.cn/Tenants/JiNing/Posts/536/newest.json?t=1777163618131', 'region': '济宁市',
             'category': '建设工程招标计划'},{  "config": {    "itemsPerPage": 20,    "currentPage": 30,    "realCurrentPage": 0  },
  "data": [    {      "title": "太白湖新区光伏储能一体化项目(一期)（EPC）",      "url": "3a20c67f-5625-1910-2d47-80943759f47e",      "date": "2026-04-22",
      "newest": true    },    {      "title": "济宁经济开发区市政道路照明设施节能降碳改造项目（二期）（EPC）",      "url": "3a20ac1d-d15f-fef5-d705-68aad6b4fada",      "date": "2026-04-17",      "newest": false    },    {      "title": "济宁经济开发区既有公共建筑节能降碳改造项目（二期）（EPC）",
      "url": "3a20ac1d-9a0f-a9d2-775c-dad356a919c1",      "date": "2026-04-17",      "newest": false    },    {
      "title": "济宁太白湖新区照明系统节能改造项目(二期)监理",      "url": "3a209d76-8660-968f-e0d5-a44be105d426",      "date": "2026-04-14",
      "newest": false    },    {      "title": "济宁太白湖新区照明系统节能改造项目(二期)EPC",      "url": "3a209d76-6e8e-0a35-b90f-93aecf01df52",
      "date": "2026-04-14",      "newest": false    },    {      "title": "太白湖新区城区排水防涝和燃气设施提升改造项目(二期） （监理）",      "url": "3a209d2b-cb8e-675b-a281-dcb5a473e06f",      "date": "2026-04-14",      "newest": false    },    {
      "title": "太白湖新区城区排水防涝和燃气设施提升改造项目(二期）EPC",      "url": "3a209d2b-b791-29e4-e1af-498f36cc2fb5",      "date": "2026-04-14",      "newest": false    },    {      "title": "山东省济宁市太白湖新区山东济宁南阳湖农场有限公司枸杞基地连体大棚建设工程(一期)",      "url": "3a207d24-b72d-d670-d097-32d87b1aa3c0",      "date": "2026-04-08",      "newest": false    },    {      "title": "共青团路（济北旅游大道改扩建工程站前路至任城界）提升工程项目设计",      "url": "3a206489-988b-96af-d538-a1d93a70cb54",      "date": "2026-04-03",      "newest": false    },    {      "title": "济宁市太白湖新区艾草产业三产融合项目项目管理",      "url": "3a205ef7-636d-2dc3-1229-0c15d5efdd5e",      "date": "2026-04-02",      "newest": false    },    {      "title": "济宁市太白湖新区艾草产业三产融合项目（EPC）",      "url": "3a205ef7-03cc-ebf3-3c54-d40674000e57",      "date": "2026-04-02",      "newest": false
    },    {      "title": "济宁北湖省级旅游度假区石桥中心小学登丰里学校建设项目监理",      "url": "3a205537-cd64-d0a6-1c1b-91458a0c66e9",      "date": "2026-03-31",      "newest": false    },    {      "title": "济宁北湖省级旅游度假区石桥中心小学登丰里学校建设项目(EPC)",      "url": "3a205537-b9dc-b5b8-05fb-5d601ece3570",      "date": "2026-03-31",      "newest": false    },    {      "title": "堃发梓轩智汇谷项目电力配套工程",      "url": "3a2054df-a3b1-d317-7a08-4f2d54bc9a43",      "date": "2026-03-31",      "newest": false    },    {      "title": "济宁高新区康泰路供热管线改造工程项目",
      "url": "3a20412b-85c8-2340-936d-bf4a3e3bde3a",      "date": "2026-03-27",      "newest": false    },    {      "title": "济宁高新区公用集团50MW/100MWh工商业储能项目（EPC）",      "url": "3a20407a-c605-6c68-e41b-325f53d0ed41",      "date": "2026-03-27",      "newest": false    },
    {      "title": "济宁高新区柳行现代智能物流园（EPC）",      "url": "3a201d62-3e91-a2d4-41b2-5680b692e0f8",      "date": "2026-03-20",
      "newest": false    },    {      "title": "山东省2026年济宁南四湖国际重要湿地中央财政湿地保护与恢复项目施工",      "url": "3a200cad-843e-a5bd-15ff-6f3985b7c47d",      "date": "2026-03-17",      "newest": false    },    {
      "title": "济宁经济开发区新能源、新材料产业园基础设施项目-配套设施10kv高压配电",      "url": "3a1fed4e-2369-de27-47df-5e06dc2a6789",      "date": "2026-03-11",      "newest": false    },
    {
      "title": "济宁经济开发区美祥路道路及配套工程",
      "url": "3a1fed09-7236-ee60-30db-5b0aa0fe9234",
      "date": "2026-03-11",
      "newest": false
    },
    {
      "title": "济宁市普通国省道多功能交通调查站项目（施工监理）",
      "url": "3a1fe3c9-2b1a-6303-ac68-2994d3d498f9",
      "date": "2026-03-09",
      "newest": false
    },
    {
      "title": "济宁市普通国省道多功能交通调查站项目（设计施工总承包）",
      "url": "3a1fe3c8-5e22-5d51-3816-1f895870e855",
      "date": "2026-03-09",
      "newest": false
    },
    {
      "title": "主城区城市防洪排涝设施改造项目(二期)监理",
      "url": "3a1fbf66-2330-0512-6128-22f80aa022a6",
      "date": "2026-03-02",
      "newest": false
    },
    {
      "title": "主城区城市防洪排涝设施改造项目（二期）施工",
      "url": "3a1fbf65-c47c-c0de-6ffd-c074744f544d",
      "date": "2026-03-02",
      "newest": false
    },
    {
      "title": "太白湖生态修复综合治理工程（EPC）",
      "url": "3a1f6868-368a-f9d9-cce0-ac04e418dcbe",
      "date": "2026-02-13",
      "newest": false
    }
  ]
}

祥情页：https://www.jnsggzy.cn/JiNing/Posts/Detail?id=3a20c67f-5625-1910-2d47-80943759f47e


            {'url_get': 'https://www.jnsggzy.cn/Tenants/JiNing/Posts/503000/newest.json?t=1777163973688', 'region': '济宁市',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/JiNing/Posts/55100101/newest.json?t=1777164045782', 'region': '济宁市',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/JiNing/Posts/551003/newest.json?t=1777164121318', 'region': '济宁市',
             'category': '济宁市其他交易'},

            # 汶上县
            {'url': 'https://www.jnsggzy.cn/Tenants/WenShang/Posts/536/newest.json?_=1777164196211', 'region': '汶上县',
             'category': '建设工程招标计划'},
            {'url': 'https://www.jnsggzy.cn/Tenants/WenShang/Posts/503000/newest.json?_=1777164276503', 'region': '汶上县',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/WenShang/Posts/551001/newest.json?_=1777164322202', 'region': '汶上县',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/WenShang/Posts/551003/newest.json?_=1777164406374', 'region': '汶上县',
             'category': '汶上县其他交易'},

            # 泗水县
            {'url': 'https://www.jnsggzy.cn/Tenants/SiShui/Posts/536/newest.json?_=1777164688806', 'region': '泗水县',
             'category': '建设工程招标计划'},
            {'url': 'https://www.jnsggzy.cn/Tenants/SiShui/Posts/503000/newest.json?_=1777164716048', 'region': '泗水县',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/SiShui/Posts/551001/newest.json?_=1777164759624', 'region': '泗水县',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/SiShui/Posts/551003/newest.json?_=1777164846527', 'region': '泗水县',
             'category': '泗水县其他交易'},

            # 高新区
            {'url': 'https://www.jnsggzy.cn/Tenants/GaoXinQu/Posts/536/newest.json?_=1777164902547', 'region': '高新区',
             'category': '建设工程招标计划'},
            {'url': 'https://www.jnsggzy.cn/Tenants/GaoXinQu/Posts/503000/newest.json?_=1777164941158', 'region': '高新区',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/GaoXinQu/Posts/551001/newest.json?_=1777164975572', 'region': '高新区',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/GaoXinQu/Posts/551003/newest.json?_=1777165027471', 'region': '高新区',
             'category': '高新区其他交易'},

            # 太白湖新区
            {'url': 'https://www.jnsggzy.cn/Tenants/TaiBaiHu/Posts/536/newest.json?_=1777165069975', 'region': '太白湖新区',
             'category': '建设工程招标计划'},
            {'url': 'https://www.jnsggzy.cn/Tenants/TaiBaiHu/Posts/503000/newest.json?_=1777165130050', 'region': '太白湖新区',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/TaiBaiHu/Posts/551001/newest.json?_=1777165174603', 'region': '太白湖新区',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/TaiBaiHu/Posts/551003/newest.json?_=1777165216103', 'region': '太白湖新区',
             'category': '太白湖新区其他交易'},

            # 梁山县
            {'url': 'https://www.jnsggzy.cn/Tenants/LiangShan/Posts/536/newest.json?_=1777165261117', 'region': '梁山县',
             'category': '建设工程招标计划'},
            {'url': 'https://www.jnsggzy.cn/Tenants/LiangShan/Posts/503000/newest.json?_=1777165369704', 'region': '梁山县',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/LiangShan/Posts/551001/newest.json?_=1777165412688', 'region': '梁山县',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/LiangShan/Posts/551003/newest.json?_=1777165458996', 'region': '梁山县',
             'category': '梁山县其他交易'},

            # 任城区
            {'url': 'https://www.jnsggzy.cn/Tenants/RenCheng/Posts/536/newest.json?_=1777165510300', 'region': '任城区',
             'category': '建设工程招标计划'},
            {'url': 'https://www.jnsggzy.cn/Tenants/RenCheng/Posts/503000/newest.json?_=1777165540609', 'region': '任城区',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/RenCheng/Posts/551001/newest.json?_=1777165572112', 'region': '任城区',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/RenCheng/Posts/551003/newest.json?_=1777165651136', 'region': '任城区',
             'category': '任城区其他交易'},

            # 经开区
            {'url': 'https://www.jnsggzy.cn/Tenants/JingKaiQu/Posts/536/newest.json?_=1777165738037', 'region': '经开区',
             'category': '建设工程招标计划'},
            {'url': 'https://www.jnsggzy.cn/Tenants/JingKaiQu/Posts/503000/newest.json?_=1777165766749', 'region': '经开区',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/JingKaiQu/Posts/551001/newest.json?_=1777165796652', 'region': '经开区',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/JingKaiQu/Posts/551003/newest.json?_=1777165824551', 'region': '经开区',
             'category': '经开区其他交易'},

            # 邹城市
            {'url': 'https://www.jnsggzy.cn/Tenants/ZouCheng/Posts/536/newest.json?_=1777165866634', 'region': '邹城市',
             'category': '建设工程招标计划'},
            {'url': 'https://www.jnsggzy.cn/Tenants/ZouCheng/Posts/503000/newest.json?_=1777165889342', 'region': '邹城市',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/ZouCheng/Posts/551001/newest.json?_=1777165923425', 'region': '邹城市',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/ZouCheng/Posts/551003/newest.json?_=1777165958875', 'region': '邹城市',
             'category': '邹城市其他交易'},

            # 曲阜市
            {'url': 'https://www.jnsggzy.cn/Tenants/QuFu/Posts/536/newest.json?_=1777166025838', 'region': '曲阜市',
             'category': '建设工程招标计划'},
            {'url': 'https://www.jnsggzy.cn/Tenants/QuFu/Posts/503000/newest.json?_=1777166096318', 'region': '曲阜市',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/QuFu/Posts/551001/newest.json?_=1777166128234', 'region': '曲阜市',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/QuFu/Posts/551003/newest.json?_=1777166161207', 'region': '曲阜市',
             'category': '曲阜市其他交易'},

            # 兖州区
            {'url': 'https://www.jnsggzy.cn/Tenants/YanZhou/Posts/536/newest.json?_=1777166210893', 'region': '兖州区',
             'category': '建设工程招标计划'},
            {'url': 'https://www.jnsggzy.cn/Tenants/YanZhou/Posts/503000/newest.json?_=1777166235291', 'region': '兖州区',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/YanZhou/Posts/551001/newest.json?_=1777166271490', 'region': '兖州区',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/YanZhou/Posts/551003/newest.json?_=1777166310861', 'region': '兖州区',
             'category': '兖州区其他交易'},

            # 嘉祥县
            {'url': 'https://www.jnsggzy.cn/Tenants/JiaXiang/Posts/536/newest.json?_=1777166381677', 'region': '嘉祥县',
             'category': '建设工程招标计划'},
            {'url': 'https://www.jnsggzy.cn/Tenants/JiaXiang/Posts/503000/newest.json?_=1777166408176', 'region': '嘉祥县',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/JiaXiang/Posts/551001/newest.json?_=1777166442550', 'region': '嘉祥县',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/JiaXiang/Posts/551003/newest.json?_=1777166493443', 'region': '嘉祥县',
             'category': '嘉祥县其他交易'},

            # 金乡县
            {'url': 'https://www.jnsggzy.cn/Tenants/JinXiang/Posts/536/newest.json?_=1777166577720', 'region': '金乡县',
             'category': '建设工程招标计划'},
            {'url': 'https://www.jnsggzy.cn/Tenants/JinXiang/Posts/503000/newest.json?_=1777166609225', 'region': '金乡县',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/JinXiang/Posts/551001/newest.json?_=1777166643617', 'region': '金乡县',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/JinXiang/Posts/551003/newest.json?_=1777166676450', 'region': '金乡县',
             'category': '金乡县其他交易'},

            # 鱼台县
            {'url': 'https://www.jnsggzy.cn/Tenants/YuTai/Posts/536/newest.json?_=1777166728464', 'region': '鱼台县',
             'category': '建设工程招标计划'},
            {'url': 'https://www.jnsggzy.cn/Tenants/YuTai/Posts/503000/newest.json?_=1777166761409', 'region': '鱼台县',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/YuTai/Posts/551001/newest.json?_=1777166795932', 'region': '鱼台县',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/YuTai/Posts/551003/newest.json?_=1777166827438', 'region': '鱼台县',
             'category': '鱼台县其他交易'},

            # 微山县
            {'url': 'https://www.jnsggzy.cn/Tenants/WeiShan/Posts/536/newest.json?_=1777166882983', 'region': '微山县',
             'category': '建设工程招标计划'},
            {'url': 'https://www.jnsggzy.cn/Tenants/WeiShan/Posts/503000/newest.json?_=1777166901489', 'region': '微山县',
             'category': '建设工程招标公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/WeiShan/Posts/551001/newest.json?_=1777166931197', 'region': '微山县',
             'category': '采购公告'},
            {'url': 'https://www.jnsggzy.cn/Tenants/WeiShan/Posts/551003/newest.json?_=1777166961656', 'region': '微山县',
             'category': '微山县其他交易'},
        ]

