/**
 * 随机取名生成器。
 *
 * 面向中文网文场景的本地词库组合生成，无需网络与模型。
 * 通过注入随机函数可以确定性测试。
 */

export type NameKind =
  | "chineseFemale"
  | "chineseMale"
  | "japanese"
  | "western"
  | "sect"
  | "technique"
  | "artifact"
  | "elixir"
  | "place";

export const NAME_KINDS: NameKind[] = [
  "chineseFemale",
  "chineseMale",
  "japanese",
  "western",
  "sect",
  "technique",
  "artifact",
  "elixir",
  "place",
];

const CHINESE_SURNAMES = [
  "李", "王", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴",
  "徐", "孙", "胡", "朱", "高", "林", "何", "郭", "马", "罗",
  "梁", "宋", "郑", "谢", "韩", "唐", "冯", "于", "董", "萧",
  "程", "曹", "袁", "邓", "许", "傅", "沈", "曾", "彭", "吕",
  "苏", "卢", "蒋", "蔡", "贾", "丁", "魏", "薛", "叶", "阎",
  "余", "潘", "杜", "戴", "夏", "钟", "汪", "田", "任", "姜",
  "范", "方", "石", "姚", "谭", "廖", "邹", "熊", "金", "陆",
  "郝", "孔", "白", "崔", "康", "毛", "邱", "秦", "江", "史",
  "顾", "侯", "邵", "孟", "龙", "万", "段", "雷", "钱", "汤",
  "尹", "黎", "易", "常", "武", "乔", "贺", "赖", "文", "卓",
  "慕容", "欧阳", "上官", "司马", "独孤", "长孙", "南宫", "西门", "东方", "皇甫",
  "尉迟", "公孙", "轩辕", "令狐", "钟离", "云", "洛", "温", "纪", "池",
];

const CHINESE_MALE_GIVEN = [
  "辰", "渊", "岳", "霄", "寒", "逸", "铭", "澜", "策", "谦",
  "恒", "铮", "衍", "鼎", "御", "瞻", "翊", "锋", "磐", "朔",
  "云舟", "景行", "长风", "望舒", "既明", "承天", "怀瑾", "慕白", "若愚", "振衣",
  "子安", "伯庸", "少陵", "元徽", "季鹰", "惊鸿", "扶摇", "孤鸿", "听澜", "踏歌",
  "远", "峻", "珩", "泓", "瀚", "叙", "搏", "驰", "疆", "烽",
  "破军", "凌虚", "望北", "归尘", "逐日", "知远", "致遥", "靖边", "定澜", "平川",
];

const CHINESE_FEMALE_GIVEN = [
  "婉", "茹", "静", "月", "雪", "霏", "璃", "烟", "凝", "黛",
  "绮", "菱", "棠", "洛", "芸", "芷", "兰", "瑶", "卿", "缨",
  "疏影", "暗香", "流萤", "拂晓", "青黛", "绛雪", "紫鸢", "碧螺", "丹朱", "素秋",
  "云舒", "月华", "霜华", "露晞", "风眠", "花间", "锦瑟", "青梧", "白芷", "朱砂",
  "窈", "姒", "姈", "媖", "嬛", "婳", "姝", "瓒", "璃", "黛",
  "初雪", "暮雨", "朝雾", "晚晴", "轻眉", "浅笑", "淡妆", "素手", "回眸", "倾城",
];

const JAPANESE_SURNAMES = [
  "佐藤", "藤原", "橘", "源", "平", "绫小路", "一条", "近卫", "鹰司", "九条",
  "白石", "青山", "黑川", "星野", "月见", "风间", "神乐", "雪代", "绯月", "天海",
];

const JAPANESE_GIVEN = [
  "樱", "薰", "辉夜", "千鹤", "雏田", "枫", "澪", "铃", "杏", "栞",
  "一护", "大和", "雅人", "直树", "健太", "翔太", "陆", "苍", "莲", "湊",
  "小夜", "深雪", "初音", "千秋", "明里", "绘里", "真昼", "宵子", "宵", "瞳",
];

const WESTERN_MALE = [
  "亚历山大", "凯", "兰斯", "艾伦", "德里克", "塞缪尔", "奥斯卡", "卢卡斯", "诺曼", "雷蒙德",
  "阿尔弗雷德", "埃德蒙", "西奥多", "朱利安", "马克西姆", "伊万", "尼古拉", "迪奥", "莱昂", "加百列",
];

const WESTERN_FEMALE = [
  "艾莉丝", "伊芙琳", "塞西莉亚", "薇薇安", "夏洛特", "艾玛", "莉迪亚", "罗莎琳", "格蕾丝", "妮可",
  "阿德莱德", "贝亚特丽斯", "克拉拉", "狄安娜", "艾尔莎", "菲奥娜", "吉赛尔", "海伦娜", "伊莎贝拉", "朱蒂丝",
];

const WESTERN_SURNAMES = [
  "温彻斯特", "格拉海姆", "霍桑", "艾德里安", "冯·罗森", "德·维尔", "范德林", "奥古斯特", "贝克", "卡特",
  "唐纳文", "埃利奥特", "菲尔米林", "加兰", "哈利维尔", "英格里斯", "朱伯特", "金罗斯", "朗斯代尔", "梅里特",
];

const SECT_PREFIX = [
  "青云", "太虚", "玄天", "凌霄", "紫霄", "落霞", "天璇", "赤霄", "万象", "无极",
  "听雨", "醉月", "寒山", "北冥", "白鹭", "观星", "问道", "藏锋", "归元", "渡厄",
  "苍梧", "流云", "浩然", "天工", "百草", "噬魂", "幽冥", "血煞", "丹霞", "剑冢",
];

const SECT_SUFFIX = ["宗", "门", "派", "阁", "谷", "山庄", "教", "寺", "观", "楼"];

const TECHNIQUE_PREFIX = [
  "天罡", "玄女", "焚天", "御风", "破军", "太阴", "紫电", "化蝶", "引雷", "碎星",
  "回春", "无相", "大衍", "周天", "九幽", "斩龙", "伏魔", "移山", "缩地", "摄魂",
];

const TECHNIQUE_SUFFIX = ["诀", "功", "剑法", "掌法", "心法", "步", "身法", "指法", "刀法", "卷"];

const ARTIFACT_PREFIX = [
  "诛仙", "寒鸦", "赤霄", "饮血", "听风", "碎星", "照夜", "溯光", "断水", "焚寂",
  "承影", "含光", "宵练", "湛卢", "纯钧", "巨阙", "龙渊", "工布", "泰阿", "干将",
];

const ARTIFACT_SUFFIX = ["剑", "刀", "枪", "弓", "鞭", "鼎", "镜", "铃", "印", "塔", "琴", "笛"];

const ELIXIR_PREFIX = [
  "九转", "凝神", "化瘀", "洗髓", "小还", "大还", "清心", "玉露", "紫金", "冰心",
  "生骨", "续命", "驻颜", "伐毛", "明目", "安魂", "破障", "淬体", "护脉", "渡厄",
];

const ELIXIR_SUFFIX = ["丹", "丸", "散", "露", "膏"];

const PLACE_PREFIX = [
  "落霞", "忘川", "碧水", "寒鸦", "云梦", "龙脊", "赤水", "孤山", "雾隐", "长风",
  "临渊", "折柳", "听涛", "枕流", "栖凤", "伏虎", "鸣沙", "流沙", "悬空", "倒悬",
];

const PLACE_SUFFIX = ["城", "镇", "谷", "岭", "湖", "泽", "山脉", "坊市", "渡口", "关"];

function pick<T>(list: T[], random: () => number): T {
  return list[Math.floor(random() * list.length)] ?? list[0];
}

function chance(probability: number, random: () => number): boolean {
  return random() < probability;
}

function generateChineseName(
  surnames: string[],
  givenBank: string[],
  random: () => number,
): string {
  const surname = pick(surnames, random);
  if (chance(0.75, random)) {
    let first = pick(givenBank, random);
    let second = pick(givenBank, random);
    // 复姓配单字名更自然；单字名也可能重复字，重抽一次。
    if (surname.length >= 2) {
      return surname + first;
    }
    if (first === second) {
      second = pick(givenBank, random);
    }
    return surname + first + second;
  }
  return surname + pick(givenBank, random);
}

function generateName(kind: NameKind, random: () => number): string {
  switch (kind) {
    case "chineseMale":
      return generateChineseName(CHINESE_SURNAMES, CHINESE_MALE_GIVEN, random);
    case "chineseFemale":
      return generateChineseName(CHINESE_SURNAMES, CHINESE_FEMALE_GIVEN, random);
    case "japanese":
      return `${pick(JAPANESE_SURNAMES, random)}${pick(JAPANESE_GIVEN, random)}`;
    case "western": {
      const given = chance(0.5, random) ? pick(WESTERN_MALE, random) : pick(WESTERN_FEMALE, random);
      return `${given}·${pick(WESTERN_SURNAMES, random)}`;
    }
    case "sect":
      return `${pick(SECT_PREFIX, random)}${pick(SECT_SUFFIX, random)}`;
    case "technique":
      return `${pick(TECHNIQUE_PREFIX, random)}${pick(TECHNIQUE_SUFFIX, random)}`;
    case "artifact":
      return `${pick(ARTIFACT_PREFIX, random)}${pick(ARTIFACT_SUFFIX, random)}`;
    case "elixir":
      return `${pick(ELIXIR_PREFIX, random)}${pick(ELIXIR_SUFFIX, random)}`;
    case "place":
      return `${pick(PLACE_PREFIX, random)}${pick(PLACE_SUFFIX, random)}`;
  }
}

/** 生成 count 个不重复的名字。 */
export function generateNames(
  kind: NameKind,
  count = 24,
  random: () => number = Math.random,
): string[] {
  const results = new Set<string>();
  let attempts = 0;
  while (results.size < count && attempts < count * 20) {
    results.add(generateName(kind, random));
    attempts += 1;
  }
  return [...results];
}
