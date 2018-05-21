from time import perf_counter as pf
import shelve

__doc__ = '''比赛逻辑
match函数输入双方名称与AI函数返回比赛结果
AI函数应接收游戏数据与自身存储空间，返回'left'，'right'或None
游戏数据格式：字典
    turnleft : 剩余回合数
    timeleft : 双方剩余思考时间
    fields : 纸片场地深拷贝
    bands : 纸带场地深拷贝
    players : 玩家信息
        id : 玩家标记（1或2）
        x : 横坐标（场地数组下标1）
        y : 纵坐标（场地数组下标2）
        direction : 当前方向
            0 : 向右
            1 : 向下
            2 : 向左
            3 : 向上
    me : 该玩家信息
    enemy : 对手玩家信息
match_with_log函数同样进行比赛，但将结果通过shelve库输出为dat文件
'''
__all__ = ['match','match_with_log']

# 参数
if 'global params':
    # 比赛规则
    MAX_TURNS = 100  # 最大回合数（双方各操作一次为一回合）
    MAX_TIME = 10  # 总思考时间（秒）
    TURNS = None  # 记录每个玩家剩余回合数
    TIMES = None  # 记录每个玩家剩余思考时间

# 游戏逻辑
if 'game logics':
    WIDTH, HEIGHT = None, None  # 游戏场地宽高
    BANDS = None  # 纸带判定区 = [[None] * HEIGHT for i in range(WIDTH)]
    FIELDS = None  # 已生成区域判定区 = [[None] * HEIGHT for i in range(WIDTH)]
    PLAYERS = [None, None]

    class player:
        '''
        玩家逻辑
        params:
            id - 向players数组中添加位置
            x, y - 初始坐标；初始纸片边长为 3
            init_direction - 初始方向，默认为 3 向上
        '''
        directions = [(1, 0), (0, 1), (-1, 0), (0, -1)]  # 方向数字对应前进方向

        def __init__(self, id, x, y, init_direction=3):
            self.id, self.x, self.y = id, x, y
            self.band_direction = []  # 记录纸带轨迹，便于状态转换时回溯
            self.direction = init_direction

            # 生成初始占有区域(l, r, u, d)
            self.field_border = [
                max(0, x - 1),
                min(WIDTH - 1, x + 1),
                max(0, y - 1),
                min(HEIGHT - 1, y + 1)]
            
            for x in range(self.field_border[0], self.field_border[1] + 1):
                for y in range(self.field_border[2], self.field_border[3] + 1):
                    FIELDS[x][y] = id

        def turn_left(self):
            '''左转'''
            self.direction = (self.direction - 1) % 4

        def turn_right(self):
            '''右转'''
            self.direction = (self.direction + 1) % 4

        def forward(self):
            '''
            向前移动一步，并相应更新场地
            returns:
                若未到达终盘条件 - None
                若到达终盘 - 
                    胜利玩家ID（1或2，None代表同时死亡）
                    终局原因编号（详见end_game函数注释）
            '''
            # 移动
            next_step = self.directions[self.direction]
            self.x += next_step[0]
            self.y += next_step[1]

            # 边缘检测
            if self.x < 0 or self.x >= WIDTH or self.y < 0 or self.y >= HEIGHT:
                return 2 - self.id, 0  # 撞墙死

            # 更新占有区域边界
            self.field_border[0] = min(self.x, self.field_border[0])
            self.field_border[1] = max(self.x, self.field_border[1])
            self.field_border[2] = min(self.y, self.field_border[2])
            self.field_border[3] = max(self.y, self.field_border[3])

            # 更新纸带碰撞
            if BANDS[self.x][self.y] is not None:
                return 2 - BANDS[self.x][self.y], 1, self.id - 1  # 纸带所有者负

            # 更新玩家碰撞
            for i in range(2):
                if PLAYERS[i].id != self.id and PLAYERS[i].x == self.x and PLAYERS[i].y == self.y:
                    if (PLAYERS[i].direction + self.direction) % 2:  # 侧碰
                        return self.id - 1, 2, PLAYERS[i].id
                    else:  # 对撞
                        return None, 3

            # 场地更新
            if FIELDS[self.x][self.y] == self.id:  # 在/回到自己场地
                if self.band_direction:
                    
                    # 1. 纸带转换为领地
                    ptrx, ptry = self.x - next_step[0], self.y - next_step[1]  # 从上一步纸带位置回溯
                    while self.band_direction:
                        BANDS[ptrx][ptry] = None
                        FIELDS[ptrx][ptry] = self.id
                        next_step = self.directions[self.band_direction.pop()]
                        ptrx -= next_step[0]
                        ptry -= next_step[1]

                    # 2. floodfill填充空腔
                    targets = set((x, y) for x in range(
                        self.field_border[0], self.field_border[1] + 1)
                                  for y in range(self.field_border[2],
                                                 self.field_border[3] + 1)
                                  if FIELDS[x][y] != self.id)
                    
                    while targets:
                        iter = [targets.pop()]
                        fill_pool = []
                        in_bound = True  # 这次填充是否为界内填充
                        while iter:
                            curr = iter.pop()
                            # floodfill
                            for dx, dy in self.directions:
                                next_step = (curr[0] + dx, curr[1] + dy)
                                if next_step in targets:
                                    targets.remove(next_step)
                                    iter.append(next_step)

                            # 判断当前点
                            if in_bound:
                                if curr[0] == self.field_border[0] or curr[0] == self.field_border[1] or curr[1] == self.field_border[2] or curr[1] == self.field_border[3]:
                                    in_bound = False
                                else:
                                    fill_pool.append(curr)

                        # 若未出界则填充内容
                        if in_bound:
                            for x, y in fill_pool:
                                FIELDS[x][y] = self.id

            else:  # 出场地
                self.band_direction.append(self.direction)
                BANDS[self.x][self.y] = self.id

        def get_info(self):
            '''
            提取玩家信息，用于传递给AI函数
            returns:
                字典，包含id，位置，方向
            '''
            return {
                'id': self.id,
                'x': self.x,
                'y': self.y,
                'direction': self.direction
            }


# 辅助函数

def init_field(k, h):
    '''
    初始化比赛场地
    params:
        k - 场地半宽（奇数）
        h - 场地高（奇数）
    '''
    # 初始化场地
    global WIDTH, HEIGHT, BANDS, FIELDS
    WIDTH = k * 2
    HEIGHT = h
    BANDS = [[None] * HEIGHT for i in range(WIDTH)]
    FIELDS = [[None] * HEIGHT for i in range(WIDTH)]

    # 初始化玩家
    PLAYERS[0] = player(1, k // 2, h // 2)
    PLAYERS[1] = player(2, k + k // 2, h // 2)

    # 初始化计时
    global TURNS, TIMES
    TURNS = [MAX_TURNS] * 2
    TIMES = [MAX_TIME] * 2

def get_params(curr_plr=None):
    '''
    生成传给AI函数的参数结构
    params:
        curr_plr - 当前玩家编号（0或1）
    return:
        字典
            turnleft : 剩余回合数
            timeleft : 双方剩余思考时间
            fields : 纸片场地深拷贝
            bands : 纸带场地深拷贝
            players : 玩家信息
                id : 玩家标记（1或2）
                x : 横坐标（场地数组下标1）
                y : 纵坐标（场地数组下标2）
                direction : 当前方向
                    0 : 向右
                    1 : 向下
                    2 : 向左
                    3 : 向上
            （在curr_plr有效时）
            me : 该玩家信息
            enemy : 对手玩家信息
            （在curr_plr有效时）
            band_route : 双方纸带行进方向
    '''
    res = {}
    res['turnleft'] = TURNS[:]
    res['timeleft'] = TIMES[:]
    res['fields'] = [l.copy() for l in FIELDS]
    res['bands'] = [l.copy() for l in BANDS]
    res['players'] = list(map(player.get_info, PLAYERS))
    if curr_plr is not None:
        res['me'] = PLAYERS[curr_plr].get_info()
        res['enemy'] = PLAYERS[1 - curr_plr].get_info()
    else:
        res['band_route'] = list(
            map(lambda plr: plr.band_direction, PLAYERS))
    return res

def parse_match(funcs):
    '''
    读入双方AI函数，执行一次比赛
    params:
        funcs - 函数列表
        
    returns:
        胜利玩家id, 终局原因编号 [, 额外描述]
        终局原因 : 
            0 - 撞墙
            1 - 纸带碰撞
            2 - 侧碰
            3 - 正碰，结算得分
            -1 - AI函数报错
            -2 - 超时
            -3 - 回合数耗尽，结算得分
    '''
    t1, t2, action = 0, 0, None  # 在字典提前初始化计时变量、存放操作结果变量，去除新建变量耗时因素

    # 建立双方存储空间
    storages = [{'log': []} for i in range(2)]

    # 执行游戏逻辑
    for i in range(MAX_TURNS):
        for plr_index in (0, 1):
            # 获取当前玩家、AI、游戏信息、存储空间
            plr = PLAYERS[plr_index]
            func = funcs[plr_index]
            params = get_params(plr_index)
            storage = storages[plr_index]

            # 执行AI返回操作符号
            try:
                t1 = pf()
                action = func(params, storage)
                t2 = pf()
            except Exception as e:  # AI函数报错
                return (2 - plr_index, -1, e)
            TURNS[plr_index] -= 1

            # 判断是否超时
            TIMES[plr_index] -= t2 - t1
            if TIMES[plr_index] < 0:
                return (2 - plr_index, -2)

            # 根据操作符转向
            if action:
                op = action[0].upper()
                if op == 'L':
                    plr.turn_left()
                elif op == 'R':
                    plr.turn_right()
                else:  # 返回值不合法
                    return (2 - plr_index, -1, Exception('返回值%r非法' % action))

            # 前进并更新结果，若终局则返回结果
            res = plr.forward()
            if res:
                return res

            # 记录log
            storages[plr_index]['log'].append(get_params(plr_index))
            storages[1 - plr_index]['log'].append(get_params(1 - plr_index))
            LOG_PUBLIC.append(get_params())

    # 回合数耗尽
    return (None, -3)

def count_score():
    '''
    统计场上面积数，用于评判胜负
    return:
        长度为2的列表，分别记录双方面积数
    '''
    res = [0, 0]
    for x in range(WIDTH):
        for y in range(HEIGHT):
            if FIELDS[x][y] is not None:
                res[FIELDS[x][y] - 1] += 1
    return res


# 主函数
def match(name1, func1, name2, func2, k=9, h=15):
    '''
    一次比赛
    params:
        name1 - 玩家1名称 (str)
        func1 - 玩家1控制函数
            接收纸片场地、纸带场地、玩家位置、玩家朝向
            返回操作符（left，right，None）
        name2 - 玩家2名称
        func2 - 玩家2控制函数
        k - 场地半宽（奇数）
        h - 场地高（奇数）
    returns:
        字典，包含比赛结果与记录信息:
            players : 参赛玩家名称
            size : 该局比赛场地大小
            log : 对局记录
            result : 对局结果，详见parse_match函数注释
    '''
    # 初始化
    init_field(k, h)
    global LOG_PUBLIC
    LOG_PUBLIC = []

    # 运行比赛，并记录终局场景
    match_result = parse_match((func1, func2))
    LOG_PUBLIC.append(get_params())

    # 如果平手则统计得分
    if match_result[0] is not None and abs(match_result[0]) == 3:
        scores = count_score()
        winner = 0 if scores[0] > scores[1] else 1 if scores[0] < scores[1] else None
        match_result = (winner, match_result[1], scores)

    # 生成对局记录对象
    return {
        'players': [name1, name2],
        'size': [WIDTH, HEIGHT],
        'log': LOG_PUBLIC,
        'result': match_result
    }

def match_with_log(*args,**kwargs):
    '''
    将比赛结果记录为dat文件，使用shelve库读取
    详见match函数注释
    '''
    # 进行比赛
    one_match = match(*args,**kwargs)

    # 输出文件
    log=shelve.open('%s-VS-%s.dat' % tuple(one_match['players']))
    for k,v in one_match.items():
        log[k]=v
    log.close()

class LogEntry:
    def __init__(self):
        self.prevBoard= None #本轮下子前的棋局
        self.turn= None #本轮下子方
        self.turnPos= None #下子位置
        self.timeCost= None #花费时间
        self.postBoard= None #下子后的棋局

    def __str__(self):
        s= '='* 20
        s+= str(self.prevBoard)
        s+= '.'* 20
        s+= '\nTurn:%s Pos:%s timeCost: %f' % (self.turn, self.turnPos, self.timeCost)
        return s
    __repr__= __str__



import os
players= []
#取得所有以T_开始文件名的算法文件名
for root, dirs, files in os.walk('.'):
    for name in files:
        if name[:2]== 'T_' and name[-3:]== '.py': #以T_开始，以.py结尾
            players.append(name[:-3]) #去掉.py后缀

for blackName in players:
    for whiteName in players:
        exec('import %s as BP' % (blackName))
        exec('import %s as WP' % (whiteName))
        match_with_log(blackName, BP.play, whiteName, WP.play)
