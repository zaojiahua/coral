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