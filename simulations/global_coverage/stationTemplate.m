function stations = stationTemplate(mode)
% 地面站名称、经纬高、最低仰角改这里。GUI 表格改的是当次运行值，不写回本文件。
% mode: 'single' 临港 / 'two' +喀什 / 'three' +佳木斯 / 'four' +海南

% 上海临港
s(1).name = 'LinGang';
s(1).lat  = dms2dd(30,54,13);
s(1).lon  = dms2dd(121,55,10);
s(1).alt  = 0;
s(1).minElevation = 15;
s(1).enabled = true;

% 喀什
s(2).name = 'KaShi';
s(2).lat  = 39.7730;
s(2).lon  = 76.5128;
s(2).alt  = 0;
s(2).minElevation = 15;
s(2).enabled = true;

% 佳木斯
s(3).name = 'JiaMuSi';
s(3).lat  = 47.99556;
s(3).lon  = 134.05789;
s(3).alt  = 0;
s(3).minElevation = 15;
s(3).enabled = true;

% 海南文昌
s(4).name = 'WenChang';
s(4).lat  = 19.6143;
s(4).lon  = 110.9511;
s(4).alt  = 0;
s(4).minElevation = 15;
s(4).enabled = true;

count = modeCount(mode);
stations = s(1:count);

end


function count = modeCount(mode)
switch char(mode)
    case 'single'
        count = 1;
    case 'two'
        count = 2;
    case 'three'
        count = 3;
    case 'four'
        count = 4;
    otherwise
        error('stationTemplate:mode', '地面站模式必须是 single、two、three 或 four。');
end
end
