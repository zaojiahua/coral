## 性能测试终点用户可以指定帧偏移

 1. 性能测试终点（图标出现-1）、【性能测试终点（图标出现-2）unit需要新增item  
 ```
 "offsetFrame": {
    "type": "uxInput",
    "order": 4,
    "content": "Tmach0 ",
    "meaning": "输入需要提前或者延后的帧数"
}
```
完整的unit是：
性能测试终点（图标出现-1）
```
{
  "tGuard": 1,
  "weight": 4,
  "timeout": 300,
  "execCmdDict": {
    "configArea": {
      "type": "jobResourceFile",
      "order": 2,
      "content": "<1ijobFile>Tmach ",
      "meaning": "记录图标搜索时所搜索的范围，需要使用选区工具选取，注意左右范围要根据画面变化趋势选取"
    },
    "configFile": {
      "type": "jobResourceFile",
      "order": 3,
      "content": "<1ijobFile>Tmach ",
      "meaning": "记录搜寻用图标，框选时不要选到背景"
    },
    "referImgFile": {
      "type": "jobResourcePicture",
      "order": 1,
      "content": "<1ijobFile>Tmach ",
      "meaning": "图片对比所用标准图片，需要使用获取图片得到 "
    },
    "offsetFrame": {
      "type": "uxInput",
      "order": 4,
      "content": "Tmach0 ",
      "meaning": "输入需要提前或者延后的帧数"
    }
  },
  "execModName": "COMPLEX",
  "jobUnitName": "end_point_with_icon_template_match",
  "functionName": "end_point_with_icon_template_match",
  "unitDescription": "性能测试终点（模板匹配）"
}
```
性能测试终点（图标出现-2）
```
{
  "tGuard": 1,
  "weight": 4.5,
  "timeout": 300,
  "execCmdDict": {
    "configArea": {
      "type": "jobResourceFile",
      "order": 2,
      "content": "<1ijobFile>Tmach ",
      "meaning": "记录图标搜索时所搜索的范围，需要使用选区工具选取，注意左右范围要根据画面变化趋势选取"
    },
    "configFile": {
      "type": "jobResourceFile",
      "order": 3,
      "content": "<1ijobFile>Tmach ",
      "meaning": "记录搜寻用图标，尽量框选范围稍稍大于图标本身"
    },
    "referImgFile": {
      "type": "jobResourcePicture",
      "order": 1,
      "content": "<1ijobFile>Tmach ",
      "meaning": "图片对比所用标准图片，需要使用获取图片得到 "
    },
    "offsetFrame": {
      "type": "uxInput",
      "order": 4,
      "content": "Tmach0 ",
      "meaning": "输入需要提前或者延后的帧数"
    }
  },
  "execModName": "COMPLEX",
  "jobUnitName": "end_point_with_icon",
  "functionName": "end_point_with_icon",
  "unitDescription": "性能测试终点"
}
```

## 双击作为性能测试起点，新增俩个unit

双击性能测试起点（点击瞬间-1）
```
{
  "tGuard": 1,
  "weight": 0.5,
  "timeout": 300,
  "execCmdDict": {
    "configArea": {
      "type": "jobResourceFile",
      "order": 2,
      "content": "<1ijobFile>Tmach ",
      "meaning": "记录图标搜索时所搜索的范围，需要使用选区工具选取，通常框选出所有图标可能出现的位置，如果测试识别效果差可以适当缩小此范围。"
    },
    "configFile": {
      "area": "-5_-14_configFile.json",
      "type": "jobResourceFile",
      "order": 3,
      "content": "<1ijobFile>Tmach ",
      "meaning": "记录要点击的图标位置处图标，需要在编辑完起终止标准图后使用选区工具选取，框选时不要选到可变的背景。"
    },
    "setShotTime": {
      "type": "uxInput",
      "order": 5,
      "content": "Tmachdefault ",
      "meaning": "输入需要拍照的时长,default代表拍到最大张数"
    },
    "referImgFile": {
      "pic": "-5_-14_referImgFile.png",
      "type": "jobResourcePicture",
      "order": 1,
      "content": "<1ijobFile>Tmach ",
      "meaning": "图片对比所用标准图片，需要点击获取图片来获取 "
    },
    "setFpsByUser": {
      "type": "uxInput",
      "order": 4,
      "content": "Tmachdefault ",
      "meaning": "输入要设置的帧率值。例需设置为60fps,则输入60即可；如无特殊要求，default代表使用默认帧率"
    }
  },
  "execModName": "COMPLEX",
  "jobUnitName": "start_point_with_point_template",
  "functionName": "start_point_with_point_template",
  "start_method": 7,
  "unitDescription": "双击性能测试起点"
}
```

双击性能测试起点（点击瞬间-2）
```
{
  "tGuard": 1,
  "weight": 1,
  "timeout": 300,
  "execCmdDict": {
    "configArea": {
      "type": "jobResourceFile",
      "order": 2,
      "content": "<1ijobFile>Tmach ",
      "meaning": "记录图标搜索时所搜索的范围，需要使用选区工具选取，通常框选出所有图标可能出现的位置，如果测试识别效果差可以适当缩小此范围。"
    },
    "configFile": {
      "type": "jobResourceFile",
      "order": 3,
      "content": "<1ijobFile>Tmach ",
      "meaning": "记录要点击的图标位置处图标，需要在编辑完起终止标准图后使用选区工具选取，请尽量框选范围稍大于图标本身。"
    },
    "setShotTime": {
      "type": "uxInput",
      "order": 5,
      "content": "Tmachdefault ",
      "meaning": "输入需要拍照的时长,default代表拍到最大张数"
    },
    "referImgFile": {
      "type": "jobResourcePicture",
      "order": 1,
      "content": "<1ijobFile>Tmach ",
      "meaning": "图片对比所用标准图片，需要点击获取图片来获取 "
    },
    "setFpsByUser": {
      "type": "uxInput",
      "order": 4,
      "content": "Tmachdefault ",
      "meaning": "输入要设置的帧率值。例需设置为60fps,则输入60即可；如无特殊要求，default代表使用默认帧率"
    }
  },
  "execModName": "COMPLEX",
  "jobUnitName": "start_point_with_point",
  "functionName": "start_point_with_point",
  "start_method": 7,
  "unitDescription": "双击性能测试起点"
}
```
