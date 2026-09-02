function satellites = satelliteTemplate(mode)
% 双星/三星轨道根数改这里。单星 TLE 在 configGlobalCoverage.m 的 cfg.satellite。
% mode: 'single' / 'multi'（multi 固定三星，后续加星时改这里）

%% 星1
s{1}.name = 'TN01A';
s{1}.ssc = 59705;
s{1}.step = 60;
s{1}.epoch = 26242.91536755;
s{1}.meanMotion = 2.00562166 * 360 / 86400;
s{1}.eccentricity = 0.0028567;
s{1}.inclination = 53.1278;
s{1}.argPerigee = 203.6024;
s{1}.raan = 167.5041;
s{1}.meanAnomaly = 156.2820;

%% 星2
s{2}.name = 'TN02A';
s{2}.ssc = 90002;
s{2}.step = 60;
s{2}.epoch = 26242.91536755;
s{2}.meanMotion = 2.00562166 * 360 / 86400;
s{2}.eccentricity = 0.0028567;
s{2}.inclination = 53.1278;
s{2}.argPerigee = 203.6024;
s{2}.raan = 212.5041;
s{2}.meanAnomaly = 66.2820;

%% 星3
s{3}.name = 'TN03A';
s{3}.ssc = 90003;
s{3}.step = 60;
s{3}.epoch = 26242.91536755;
s{3}.meanMotion = 2.00562166 * 360 / 86400;
s{3}.eccentricity = 0.0028567;
s{3}.inclination = 53.1278;
s{3}.argPerigee = 203.6024;
s{3}.raan = 257.5041;
s{3}.meanAnomaly = 336.2820;

%% 模板
switch char(mode)
    case 'single'
        count = 1;
    case 'multi'
        count = 3;  % 固定三星
    otherwise
        error('satelliteTemplate:mode', '卫星模式必须是 single 或 multi。');
end

satellites = s(1:count);

end
